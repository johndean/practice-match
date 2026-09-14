# The VIN Foundation Admin Control Surface — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every administrative act the backend already performs — and the one, Requests, that it does not perform at all yet — gets a screen composed from V3's own elements, so that D-C53 ("all the admin tabs must be factual and fully functional, zero-gaps, zero-fake data, everything must be surfaced and wired to UX") is true of the whole control surface rather than of four tables.

**Architecture:** Seven amendment families — **A41** (Settings tab + the re-authentication dialog), **A42** (the licence decision), **A43** (Requests: model, routes, four surfaces, admin tab), **A44** (user detail + Access), **A45** (listing detail), **A46** (permissions matrix + tokens), **A47** (the seller application) — plus the held **A40.1/A40.2** doors and the ninth declared prototype prop. Each family is a set of literal edits applied to the approved design through the D15 mechanism (`frontend/tests/design-amendments.ts` → `npm run gen:design` → `gen:logic` → `gen:app`), each with one `LOCAL_AMENDMENTS.md` row per entry and an oracle so the approved states keep their pixels. The one genuinely new subsystem is **Requests**: one migration, one router, one deferred arm in `seller_listings.read_document` that has been documented as "the arm that will be added when a `request` table exists" since Task SL7.

**Tech Stack:** the design bundle's own dc runtime (React 18 + `support.js`) on the reference side · Vue 3 + `frontend/scripts/convert-dc.mjs` on the app side · FastAPI + psycopg2 + SQLAlchemy · PostgreSQL 16 / PostGIS · Redis · Vitest 3 · Playwright (`reference-baselines.spec.ts`, `visual.spec.ts`, `dom.spec.ts`, `smoke.spec.ts`) · pytest.

**Branches:** one worktree per family, each cut from `main` at the time that family starts. Implementers never push, deploy or run `railway`; the controller does those at hand-back.

---

## The source of truth

`docs/superpowers/specs/2026-09-13-admin-control-surface-design.md`, whose **§10 was ruled by the controller on 2026-09-14**. None of those five is reopened here:

| # | Ruled |
|---|---|
| 10.1 | **Hide the two doors a buyer cannot open — YES, sequenced LAST** (after A47), so there is time to reverse it. It re-pins seven of the thirteen frozen design screens and adds a ninth declared prototype prop. |
| 10.2 | **The seller-application screen lands AFTER A43** (Requests). |
| 10.3 | **Suspend does NOT get a step-up.** `REAUTH` keeps its six actions exactly as `app/auth/permissions.py` declares them. |
| 10.4 | **The pets 0.57 factor is a methodology note**, not a `dataset_registry` row. *(Not this plan's work; recorded so nobody adds a row here.)* |
| 10.5 | **Neither Esri row is decided by the product.** A42 gives the Data Sources tab its Clear / Block, re-authenticated, with a mandatory note; the VIN Foundation decides. Until they do the Satellite toggle stays exactly as shipped. |

Above the spec sit John's standing rulings: **D-C53** (2026-09-13, the ask), **D-C54** (the `admin` role holds every permission — `MATRIX = {perm: holders | _ADMIN …}`), and the two design rules CLAUDE.md carries verbatim: *reference open first, port verbatim, absent beats faked* and *real data or NO rows*.

### The amendment family ids, and how they were derived

**A41–A47**, per spec §9, plus **A40.1/A40.2** which have been RESERVED AND UNWRITTEN since 0.1.23 and whose ids may not be reused. Re-derive before writing a line in any family:

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/<this family's worktree>"
grep -c "id: 'A4" frontend/tests/design-amendments.ts          # A40.3-A40.6 exist; A41+ must be 0 before you start
for f in A41 A42 A43 A44 A45 A46 A47; do
  printf '%s design-amendments: %s  ledger: %s\n' "$f" \
    "$(grep -c "id: '$f" frontend/tests/design-amendments.ts)" \
    "$(grep -c "^| $f" docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md)"
done
python3 - <<'PY'
import re, pathlib
md = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md").read_text(encoding="utf-8")
fams = sorted({int(re.match(r"A(\d+)", c).group(1))
               for line in md.split("\n") if line.startswith("| ")
               for c in [line.split("|")[1].strip()] if re.fullmatch(r"A\d+(\.\w+)*", c)})
print("families in the ledger:", fams)
PY
```

Expected at plan-cut time (`main` at `3a318aa`): every A41–A47 count is `0`. **A36, A38, A39 and A48 are in flight on their own branches and A37 is reserved and unwritten.** If a count for YOUR family is not `0`, `main` has moved: STOP and re-derive — do not renumber on your own judgement.

### The controller's decisions taken while writing this plan

Each is a place the spec named a fact but not a mechanism. Each is reversible by John; each is recorded so he can see what he is reversing.

| # | Decision |
|---|---|
| **D1** | **Settings row 1 (`MARKET_DATA_PUBLIC`) is READ-ONLY — no Turn on / Turn off button.** It is a Railway environment variable (`app/config.py:33`), there is no route that writes it, and `scripts/verify-deploy.sh` refuses a production deploy where it is true. A button that cannot complete must not be drawn (spec §1 rule 3). The row states the value, the environment it is set in, and that it is set in Railway. |
| **D2** | **Settings row 2 gets a NEW route**, `POST /api/admin/vintages/{dataset_key}/activate`, guarded by `engine.activate` (already in `MATRIX`, `REAUTH` and `AUDITED`) and delegating to `app.census.vintage.activate`, which is the existing CLI's own function. `engine.activate` was a permission with no HTTP route at all. |
| **D3** | **`GET /api/admin/settings` is guarded by `data_sources.read`**, and a pytest pins `MATRIX["data_sources.read"] == MATRIX["signups.read"] == MATRIX["page.admin"]` so the day those three diverge the aggregate read fails loudly instead of leaking one row's facts to a holder of another row's permission. |
| **D4** | **The Settings tab carries NO badge** (`count: null`, so A36.3/A38.3a/A39.3a's `hasCount` `sc-if` unmounts the lozenge). Settings is not a queue. |
| **D5** | **Settings row 4's sub-line carries no token count until Manage has been opened once.** `tokens.manage` is in `REAUTH`, so a count on first paint would demand a password to render a screen. Before Manage, the sub-line is the design's own em-dash; after the re-auth succeeds, it is the served count. |
| **D6** | **The admin Requests tab's Age sub-line is the LAST EVENT's own kind** from `request_event`, in the design's vocabulary, and is absent where there is none. The design's four fixture sub-lines ("Reminder sent", "Packet released", "Under contract elsewhere", "No action yet") stay in the oracle only; "Reminder sent" can never be produced because no reminder job exists (spec §5). |
| **D7** | **The drill-down (A44/A45) is an `sc-if`-gated aside inside the admin shell, not a route.** The admin screen keeps its URL, so `frontend/src/router/sync.ts` needs no change and the four frozen `admin-*` captures keep their pixels while it is closed. |
| **D8** | **The seller-application card (A47) collects `license_state` as well as the spec's four fields.** `app/api/applications.SELLER_REQUIRED` is `("practice_name", "license_state")` and `ATTESTATION["seller"]` is `"ownership_attestation"`; a form that omits a field the route requires cannot complete. `city`, `zip` and `timing` ride along in `fields` as the spec asks. |
| **D9** | **The reference's nav filter reads a TWO-ROW prototype table pinned against `MATRIX` by pytest.** The design must state no role test of its own (A40's rule), and the reference receives no adapter — so the design carries `PROTOTYPE_NAV_ROLES = { "page.admin": ["staff", "admin"], "page.seller": ["seller", "admin"] }` as the prototype's own fixture, used ONLY when `this.props.perms` is absent, and `tests/auth/test_permissions.py` pins both rows against `app.auth.permissions.MATRIX`. This is A22's ownership-tuple mechanism and A33.3's geography-phrase mechanism, not a second copy of the matrix. |
| **D10** | **A42's mandatory note is mandatory in the DIALOG, not in the API.** `LicenseDecision.notes` stays optional — it is a published contract other callers hold (`docs/integrations/market-data-api.md`) — and the dialog refuses an empty note for a licence decision. |
| **D11** | **The Settings tab draws ONE ROW PER REGISTERED DATASET, not one "Census data vintage" row.** The spec's single row could offer only one dataset's button; each dataset has its own active vintage, its own last load and its own activation. The `Setting` cell carries the registry's own `display_name`. |
| **D12** | **The Settings tab, the re-auth dialog and every drill-down have a REAL-BROWSER gate and no zero-pixel gate.** `frontend/tests/screens.ts` runs identical clicks on both targets, and the reference is the raw bundle with `?props=` and **receives no adapter**, so a surface that exists only with an adapter cannot be an approved state. They are captured in `frontend/tests/smoke.spec.ts` instead. This is the gap A27.7 already carries, for the same reason; it is stated in every affected task rather than discovered. The ONE exception is A47's gate card (Task 23), which is driven by `startGate` and IS an approved state. |

---

## Global Constraints

Every task's requirements implicitly include this section. Values are copied verbatim from CLAUDE.md, the spec, or the code they pin.

### The rules every composition obeys (spec §1)

1. **Reference open first, port verbatim, absent beats faked.** A composition reuses an element V3 already carries, in the declarations V3 gives it, in the place V3's own idiom would put it. The eight account screens (A8) are the precedent and the proof.
2. **Real data or NO rows.** With an adapter present a surface renders what the API answered or nothing — never a fixture (A16.1 / A17.1's ternary, keyed on adapter PRESENCE and never on data). The reference and the Claude Design preview pass no adapter and keep V3's fixtures.
3. **An action renders only if it completes.** A button calls a real route with a real transition and, where the permission is in `AUDITED`, an audit row — or it is not drawn.
4. **Step-up before harm.** Every action in `permissions.REAUTH` — `licence.decide`, `engine.activate`, `roles.grant`, `tokens.manage`, `users.revoke`, `signups.notify` — passes through the A41 dialog. **Suspend does NOT** (ruling 10.3).
5. **Every view of sensitive content is logged.** `GET /api/admin/requests/{id}/message` writes an `audit_log` row BEFORE it answers.
6. **The frozen thirteen.** `mobile-list`, `mobile-detail`, `detail`, `requests`, `seller-dash`, `wizard-step-1`, `wizard-step-7`, `wizard-preview`, `wizard-done`, `admin-users`, `admin-listings`, `admin-requests`, `admin-data-sources`. A moved hash means the change leaked: **stop with NEEDS_CONTEXT, do not re-pin** — except in Task 25, the ONE ruled re-pin, which names its seven rows one by one.

### The repo's standing rules

- **(a) `frontend/src/logic.js` is NEVER hand-edited, and neither is any bundle file.** Every change to the design is an entry in `frontend/tests/design-amendments.ts`, applied to the pristine copy by `npm run gen:design`, after which `npm run gen:logic` re-ports the script and `npm run gen:app` regenerates `App.vue`/`pseudo.css`; `frontend/tests/app-generated.test.ts` proves byte equality. `Practice Match V3.rev2.dc.html` and `MarketMapV3.rev2.jsx` are pristine and are never edited. **No task in this plan touches `MarketMapV3.jsx`.**
- **(b) Every amendment's `find` is counted as a FIXED STRING before it is written, with Python and never `grep -c -F`** (`grep` splits on newlines and would OR a multi-line `find`):
  ```bash
  python3 -c "import pathlib,sys; print(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').count(open(sys.argv[2],encoding='utf-8').read()))" \
    "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" /tmp/anchor.txt
  ```
  `applyAmendments` throws if the count at the point of application is wrong; the point of the rule is to know BEFORE the run. Every task below gives the command that PRINTS its anchor.
- **(c) 100 % coverage, both sides, warnings as errors.** Backend, exactly as CI runs it:
  ```bash
  docker compose -f docker-compose.dev.yml up -d
  poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m "not timing"
  poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m timing -p no:randomly --cov-append --cov-report=xml --cov-fail-under=100
  ```
  Frontend, **BUILD BEFORE TEST** (`vue-only.test.ts` and `bundle-budget.test.ts` read `frontend/dist/_app`):
  ```bash
  cd frontend && npm run typecheck && npm run build && npm test     # npm test IS `vitest run --coverage`, the exact CI step
  ```
  `logic.js` is excluded from the measured set (it is the design's script) but every new branch in it is characterised in `frontend/src/logic.test.ts` regardless.
- **(d) Zero pixel tolerance, never relaxed.** `maxDiffPixels: 0` beside `threshold: 0.1` in `frontend/tests/playwright.config.ts` stays. Baselines regenerate from the amended design in the same run (`npm run test:visual:baselines`, the `reference` project), so a ruled change is legal there; a failure AFTER regeneration means the app and the design diverged — stop and diff, never widen the tolerance.
- **(e) No suppressions.** No `// eslint-disable`, no `# type: ignore`, no `test.skip`, no `it.skip`, no `xfail`, no `--cov-fail-under` below 100, no `pragma: no cover` added to make a gate green. A gate that cannot be made green as written is a NEEDS_CONTEXT.
- **(f) A guard must test the sentinel the producer actually emits.** Before writing any guard, run the real producer and print what it returns. Two this plan leans on, measured at `3a318aa`:
  - `permissions.effective_roles` returns `frozenset({'applicant'})` for **every** state but `active`, which is why `loadAdmin`'s guard does not restate `me.state === "active"`.
  - `frontend/src/auth/can.ts::can()` **THROWS** for a permission not in `MATRIX`. A typo in a `perm:` string is a `pageerror` Playwright fails on — deliberately, not a silent `false`.
- **(g) NEVER edit an applied migration.** `scripts/migrate.py` records each file's SHA-256 and refuses a tree whose bytes moved. New files only. **The free range is `097` and up** (see `docs/MIGRATIONS.md`, the one ledger — `092`–`094` are `feat/admin-data-sources`, `095` is `fix/census-204`): `migrations/` on `main` ends at `091_listing_provenance.sql`, and across every branch in the repo (`040`–`042` on the identifiability branches, `092`–`093` on `feat/admin-data-sources`) the highest claimed is **095**. This plan reserves **`096_request.sql`** (Task 8) and nothing else; claim it by adding its row to `docs/MIGRATIONS.md` in the same commit.
- **(h) NO VERSION BUMP.** `frontend/package.json` and `pyproject.toml` stay at whatever `main` carries (0.1.25 at `3a318aa`). The lockstep bump and the release are the controller's, after acceptance. `tests/test_versions.py` keeps the two in step either way.
- **(i) Playwright ports and databases never collide across worktrees, and there is NEVER a second compose stack.** The one dev stack is `docker compose -f docker-compose.dev.yml` on **5433** (Postgres) and **6380** (Redis) and it is shared; never start another on those ports or any other, and never `FLUSHDB` it. Each family exports, explicitly, in every shell that runs Playwright:

  | Family | `PW_APP_PORT` / `PW_REF_PORT` / `PW_CS_PORT` | `PW_API_PORT` | database | Redis db |
  |---|---|---|---|---|
  | A41 | 5603 / 5604 / 5605 | 8177 | `practice_match_a41` | `/12` |
  | A42 | 5613 / 5614 / 5615 | 8187 | `practice_match_a42` | `/13` |
  | A43 | 5623 / 5624 / 5625 | 8197 | `practice_match_a43` | `/14` |
  | A44 | 5633 / 5634 / 5635 | 8207 | `practice_match_a44` | `/15` |
  | A46 | 5653 / 5654 / 5655 | 8227 | `practice_match_a46` | `/12` — only after A41 has merged and its worktree is removed |
  | A45 | 5643 / 5644 / 5645 | 8217 | `practice_match_a45` | `/13` — only after A42 has merged and its worktree is removed |
  | A47 | 5663 / 5664 / 5665 | 8237 | `practice_match_a47` | `/14` — only after A43 has merged and its worktree is removed |
  | doors | 5673 / 5674 / 5675 | 8247 | `practice_match_doors` | `/15` — only after A44 has merged and its worktree is removed |

  Redis has sixteen databases and siblings already hold `/0`, `/3`, `/7`–`/11`. **The four re-uses are conditional and the condition is stated in the table: never take a db whose prior holder's worktree still exists.** Every shell:
  ```bash
  export PW_APP_PORT=<from the table> PW_REF_PORT=<…> PW_CS_PORT=<…> PW_API_PORT=<…>
  export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/<from the table>
  export REDIS_URL=redis://localhost:6380/<from the table>
  for p in $PW_APP_PORT $PW_REF_PORT $PW_CS_PORT $PW_API_PORT; do
    lsof -nP -iTCP:$p -sTCP:LISTEN && { echo "PORT $p BUSY — pick another and record it here"; exit 1; }
  done
  git worktree list | grep -q "<the prior holder's worktree>" && { echo "prior holder still exists — do not take its Redis db"; exit 1; }
  ```
  **pytest and Playwright never share a database**: pytest clones per test from a template (`tests/conftest.py::scratch_dsn`) off `DATABASE_URL`, and `frontend/tests/targets.ts` runs `migrate.py` + `reset_rate_limits.py` + `seed_persona.py` + `seed_listings.py` against whatever `DATABASE_URL` names.
- **(j) A hand-maintained number in a comment or a document is a defect waiting to happen.** Counts in this plan are stated as **deltas** off a value measured when the task starts, never as absolutes typed at plan-cut time. The invariants are arithmetic and do not rot: `entries = literals + A1's derived count` · `ledger rows = literals + 1` · `baselines = screens.ts entries` · `families = distinct numbered ids in design-amendments.ts, PLUS ONE for A1`.
- **(k) Surgical diffs, no destructive actions, conventional commits with explicit pathspecs.** `git add <path> …`, never `git add -A`. Every commit ends with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Implementers never `git stash`, never touch another worktree, and never push.
- **(l) Merge `main` before the final push, and merge ledger branches one at a time.** `design-amendments.ts`, `design-amendments.test.ts`, `LOCAL_AMENDMENTS.md` and CLAUDE.md's two byte-identical copies collide on every amendment branch, and several are in flight. Merge `main` into the branch before the family's last task pushes, re-run `npm run remap:citations`, and re-take every derived count after the merge.
- **(m) CI is polled in the FOREGROUND.** A subagent never receives a background-completion notification. Any wait on `gh run` is a bounded foreground loop:
  ```bash
  for i in $(seq 1 40); do
    out=$(gh run list --branch "$BRANCH" --commit "$SHA" --json name,status,conclusion 2>/dev/null)
    echo "$out"
    printf '%s' "$out" | grep -q '"status":"in_progress"' || printf '%s' "$out" | grep -q '"status":"queued"' || break
    sleep 30
  done
  ```
  Four jobs `success`, READ, not assumed.
- **(n) Deviations STOP.** A `find` that does not match with `count: 1` at its point of application, a frozen hash the plan did not predict, an unpredicted re-based state, a DOM-oracle line after regeneration, a coverage gate that needs relaxing — stop and report as NEEDS_CONTEXT. Do not improvise.
- **(o) AMEND-GUARD tokens are WORDS, not hints.** `frontend/tests/amend-guard.ts` walks every line and every prose sentence an entry's `replace` introduced and fails unless it is still in the amended design or a later row DECLARES the removal. The LINE tier takes `Consumes <id>` (or the stronger `Supersedes <id>`); the SENTENCE tier takes only `Supersedes <id>`, or `Superseded by <id>` on the entry being retired. **A bare mention of an id is not a declaration and neither is a citation.** `LOCAL_AMENDMENTS.md`'s own header says how to write a row and a citation; read it before writing one.
- **(p) Legally load-bearing, and untouched by this plan.** Attribution stays visible on every map and under Community Context; blocked datasets never ship; the Esri-vs-CARTO basemap licence is ONE open decision record in `docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md` and is not swapped either way. A42 gives the Foundation the button and takes no decision for them.

---

## The closing sequence (every family's LAST task runs this, in full)

Written out once here and named, so no task ever says "the same as task N". Every reference below is to THIS block, and its content is complete.

- [ ] **C1 — the ledger rows.** `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md` gains ONE row per entry, in apply order, each with its `V3:<line>` citation and, where the entry's `find` takes text an earlier entry's `replace` put there, the `Consumes <id>` token **on its own row**. Read the file's "How to write a row" header first — a bare mention of an id is not a declaration, and neither is a citation.
- [ ] **C2 — re-map every citation.**
  ```bash
  cd frontend && npm run remap:citations
  ```
  An entry whose `replace` is longer than its `find` moves every design line below it, and every citation with them. The tool re-takes every number against the amended design, prints what it moved, and REFUSES rather than guesses; the answer to a refusal is a row in `frontend/tests/citation-pins.json` naming the line by a neighbouring distinctive anchor and saying why — never a hand edit. Commit what it moved in the same commit.
- [ ] **C3 — CLAUDE.md, in BOTH byte-identical copies.** Add the family's paragraph and re-take the counts sentence FROM THE LEDGER, never by arithmetic:
  ```bash
  python3 - <<'PYEOF'
  import re, pathlib
  md = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md").read_text(encoding="utf-8")
  ids = [l.split("|")[1].strip() for l in md.split("\n")
         if l.startswith("| ") and re.fullmatch(r"A\d+(\.\w+)*", l.split("|")[1].strip())]
  fams = {re.match(r"A(\d+)", i).group(1) for i in ids}
  print("ledger rows:", len(ids), "families:", len(fams), "literals:", len(ids) - 1)
  PYEOF
  ```
  Write both copies from ONE string; `tests/test_docs.py` pins the count and the byte equality of the two copies.
- [ ] **C4 — merge `main`, then regenerate.** Ledger branches collide on `design-amendments.ts`, `design-amendments.test.ts`, `LOCAL_AMENDMENTS.md` and CLAUDE.md's two copies, and several are in flight.
  ```bash
  git merge --no-edit main
  cd frontend && npm run gen:design && npm run gen:logic && npm run gen:app && npm run remap:citations
  ```
  Re-take every derived count after the merge.
- [ ] **C5 — every gate, in the order CI runs them (BUILD BEFORE TEST).**
  ```bash
  docker compose -f docker-compose.dev.yml up -d
  poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m "not timing"
  poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m timing -p no:randomly --cov-append --cov-report=xml --cov-fail-under=100
  cd frontend && npm run typecheck && npm run build && npm test
  npm run test:visual:baselines && npm run test:e2e
  ```
- [ ] **C6 — the baseline-hash diff, against the Preconditions map.**
  ```bash
  node -e '
  const {createHash}=require("crypto"),{readdirSync,readFileSync}=require("fs"),{join}=require("path");
  const before=JSON.parse(readFileSync(process.env.PRE,"utf8")), d="tests/visual.spec.ts-snapshots";
  let moved=0;
  for (const f of readdirSync(d).sort()) {
    const h=createHash("sha256").update(readFileSync(join(d,f))).digest("hex");
    if (!(f in before)) { console.log("APPENDED", f); continue; }
    if (before[f]!==h) { console.log("MOVED", f); moved++; }
  }
  console.log(moved+" moved");' PRE="$SCRATCH/<family>-baselines-before.json"
  ```
  **The MOVED list must equal the list the task predicted, exactly.** Anything else is a NEEDS_CONTEXT, and `frontend/tests/baseline-manifest.json` is never re-pinned outside Task 25.
- [ ] **C7 — commit with an explicit pathspec, and hand back.** `git add <path> ...`, never `git add -A`; every commit ends with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. The hand-back carries: the base SHA, the final SHA, C6's output, every entry id with its ledger row, and every deviation stopped on. **Implementers never push, never deploy and never run `railway`.**

---

## Preconditions (run once per family, before any design edit)

```bash
cd "/Users/johndean/Development/Practice Match"
git worktree add .worktrees/<family-worktree> -b feat/<family-branch> main
cd .worktrees/<family-worktree>
git log --oneline -1                       # the base; record it in the hand-back

# The family id is free (see "The amendment family ids" above)
# The dev stack is up and the per-family database exists
docker compose -f docker-compose.dev.yml up -d
export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/<db from the ports table>
createdb -h localhost -p 5433 -U pm "$(basename "${DATABASE_URL}")" 2>/dev/null || true
poetry run python scripts/migrate.py

# The pre-change baseline hash map — every re-base claim in this plan is MEASURED against it
# (A33's discipline), never reasoned about.
export PW_APP_PORT=<this family's row in the ports table> PW_REF_PORT=<same row> PW_CS_PORT=<same row> PW_API_PORT=<same row>
export REDIS_URL=redis://localhost:6380/<this family's Redis db, same row>
cd frontend && npm run test:visual:baselines
node -e '
const {createHash}=require("crypto"), {readdirSync,readFileSync,writeFileSync}=require("fs"), {join}=require("path");
const d="tests/visual.spec.ts-snapshots", out={};
for (const f of readdirSync(d).sort()) out[f]=createHash("sha256").update(readFileSync(join(d,f))).digest("hex");
writeFileSync(process.env.PRE, JSON.stringify(out,null,2)+"\n");
console.log(Object.keys(out).length+" baselines hashed");
' PRE="$SCRATCH/<family>-baselines-before.json"
```

`$SCRATCH` is this session's scratchpad directory; record the path in the hand-back. Expected: **one hash per `screens.ts` entry** — derive it, never type it.

---

## File Map

| File | Kind | Responsibility | Task |
|---|---|---|---|
| `app/api/admin_settings.py` | create | `GET /api/admin/settings`, `POST /api/admin/vintages/{key}/activate` | 1 |
| `app/main.py` | modify | mount the new routers | 1, 8, 10 |
| `tests/api/test_admin_settings.py` | create | the settings read and the activation | 1 |
| `frontend/src/admin/settings.ts` | create | `GET /api/admin/settings` → the Settings tab's rows; `activate()` | 2 |
| `frontend/src/admin/reauth.ts` | create | `ReauthUi` — the one place a step-up action is wrapped | 2 |
| `frontend/src/app.setup.js` | modify | the `adminSettings`, `reauth`, `requests`, `sellerRequests`, `adminRequests`, `adminUserDetail`, `adminListingDetail`, `adminTokens`, `sellerApply` props | 2, 11, 14, 18, 20, 22 |
| `frontend/tests/design-amendments.ts` | modify | every family's entries, appended as the last family block | 3–7, 12–13, 15–16, 19, 21, 23–24 |
| `frontend/tests/design-amendments.test.ts` | modify | the ids in `AMENDMENT_IDS`, the `toHaveLength` count, each family's structural case | same |
| `docs/design-reference/…/Practice Match V3.dc.html` | **regenerated** | `npm run gen:design` | same |
| `frontend/src/logic.js`, `App.vue`, `generated/pseudo.css`, `app.setup.js` | **re-ported / regenerated** | `npm run gen:logic`, `npm run gen:app` — never hand-edited | same |
| `frontend/src/logic.test.ts` | modify | one characterisation per entry | same |
| `frontend/tests/screens.ts` | modify | the appended approved states | 5, 7, 13, 16, 19, 21, 23 |
| `frontend/tests/harness.ts` | modify | the new collection stubs, per tab | 5, 7, 13, 16, 19, 21, 23 |
| `frontend/tests/design-admin-settings.mjs`, `design-admin-requests.mjs`, `design-admin-tokens.mjs` | create | the oracle fixtures, derived from `adminVals()` | 5, 13, 19 |
| `migrations/096_request.sql` | create | `request` + `request_event` | 8 |
| `app/api/requests.py` | create | buyer + seller + admin request routes | 8, 9, 10 |
| `app/api/seller_listings.py:1251-1297` | modify | the buyer-with-an-accepted-request arm of `read_document` | 9 |
| `app/api/auth.py:287-302` | modify | `me_payload` gains `license_state` | 10 |
| `frontend/src/requests/buyer.ts`, `seller.ts` | create | the two member-facing adapters | 11 |
| `frontend/src/admin/requests.ts` | create | `GET /api/admin/requests` → the Requests tab | 11 |
| `frontend/src/admin/user_detail.ts`, `listing_detail.ts`, `tokens.ts` | create | the drill-down adapters | 14, 20, 18 |
| `frontend/src/admin/permissions.ts` | modify | the matrix view's grid and `headStyle` | 18 |
| `frontend/src/auth/seller_apply.ts` | create | the seller application adapter | 22 |
| `docs/design-reference/…/LOCAL_AMENDMENTS.md` | modify | one row per entry, in apply order | every design task |
| `CLAUDE.md` | modify | the family paragraph and the derived count sentence, in BOTH byte-identical copies | last task of each family |
| `docs/integrations/market-data-api.md` | modify | the new admin routes | 1, 10, 17 |

---

## Task index

| # | Family | Title |
|---|---|---|
| 1 | A41 | The settings read and the vintage activation (backend) |
| 2 | A41 | `admin/settings.ts` and `admin/reauth.ts` (frontend adapters) |
| 3 | A41 | The fifth tab — A41.1–A41.4 |
| 4 | A41 | The re-authentication dialog — A41.5–A41.11 |
| 5 | A41 | Revoke through the dialog, the two real-browser states, the ledger |
| 6 | A42 | `decideLicense` on the data-sources adapter, and the dialog's note slot |
| 7 | A42 | Clear / Block on the Data Sources tab — the oracle and the ledger |
| 8 | A43 | `migrations/096_request.sql` and the buyer routes |
| 9 | A43 | The seller routes, and the document packet the accept releases |
| 10 | A43 | The admin routes, and `/api/me`'s two served facts |
| 11 | A43 | `requests/buyer.ts`, `requests/seller.ts`, `admin/requests.ts` |
| 12 | A43 | The three member surfaces — A43.1–A43.9 |
| 13 | A43 | The admin Requests tab — A43.10–A43.14 |
| 14 | A44 | `admin/user_detail.ts` |
| 15 | A44 | The drill-down panel and its Overview/History tabs — A44.1–A44.6 |
| 16 | A44 | The Access tab and the role grant — A44.7–A44.10 |
| 17 | A46 | `GET /api/admin/tokens` |
| 18 | A46 | `admin/tokens.ts` and the matrix view's layout |
| 19 | A46 | Settings rows 4 and 5, and the matrix view — A46.1–A46.7 |
| 20 | A45 | `admin/listing_detail.ts` |
| 21 | A45 | The listing drill-down — A45.1–A45.4 |
| 22 | A47 | `auth/seller_apply.ts` |
| 23 | A47 | The seller-application card — A47.1–A47.6 |
| 24 | doors | The ninth prototype prop and the nav filter — A40.1/A40.2 |
| 25 | doors | The ruled re-pin of seven frozen captures |

**Order.** 1→2→3→4→5 (A41) first. Then **A42 (6→7), A43 (8→9→10→11→12→13), A44 (14→15→16) and A46 (17→18→19) in parallel.** Then A45 (20→21) after A44, A47 (22→23) after A43, and 24→25 LAST.

---

## Task 1: The settings read and the vintage activation (A41, backend)

`engine.activate` has been a permission with **no HTTP route** since Task I5 — reachable only from `scripts/census_load.py activate`. This task gives it one, and gives the Settings tab the single read behind its three rows. Nothing in the design changes.

**Re-basing states: NONE.** **The thirteen frozen hashes must not move** (nothing renders differently).

**Files:**
- Create: `app/api/admin_settings.py`
- Modify: `app/main.py:136` (mount the router beside `admin_data_sources_router`, inside the same `site_mode == "app"` block and with the same reason)
- Modify: `docs/integrations/market-data-api.md` (the two new routes, in the `/api/admin/data-sources` section's own shape)
- Test: `tests/api/test_admin_settings.py` (create), `tests/auth/test_permissions.py` (the D3 pin), `tests/api/test_contract_doc.py` (unchanged file, new rows exercised)

**Interfaces:**
- Consumes: `app.census.vintage.activate(conn, dataset_key, vint, by, *, force=False, note=None) -> Report`, `app.census.vintage.ActivationRefused`, `app.census.vintage.TABLE_FOR: dict[str, str]`, `app.auth.deps.require(perm)`, `app.auth.audit.write(conn, *, actor, action, target_type, target_id=None, before=None, after=None, reason=None, request=None)`.
- Produces, from `app/api/admin_settings.py`:
  ```python
  router: APIRouter                       # prefix "/api/admin"
  MARKET_FLAG_SOURCE: str                 # "Railway environment variable MARKET_DATA_PUBLIC"

  # GET  /api/admin/settings                      -> SettingsPayload (below), guarded data_sources.read
  # POST /api/admin/vintages/{dataset_key}/activate -> ActivationPayload, guarded engine.activate
  ```
  `SettingsPayload` as JSON, which **Task 2's `frontend/src/admin/settings.ts` types verbatim**:
  ```jsonc
  {
    "market_data_public": { "value": false, "environment": "qa",
                            "set_in": "Railway environment variable MARKET_DATA_PUBLIC", "writable": false },
    "vintages": [ { "dataset_key": "acs5", "display_name": "…", "active_vintage": "2019–2023",
                    "activated_at": "…Z|null", "activated_by": "…|null", "activation_note": "…|null",
                    "loaded_vintage": "2020–2024|null", "last_load_finished_at": "…Z|null",
                    "activatable": true } ],
    "signups": { "total": 0, "launch_mailed": 0, "not_mailed": 0,
                 "last_mailed_at": "…Z|null", "sendable": true }
  }
  ```
  `ActivationPayload`: `{ "dataset_key", "vintage", "prior_vintage", "rows", "ratio", "note" }`. Refusals carry decision A5's `{"error": {"code", "message"}}`: `BAD_DATASET` 422, `NOTE_REQUIRED` 422, `ACTIVATION_REFUSED` 409.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_admin_settings.py`:

```python
"""GET /api/admin/settings and POST /api/admin/vintages/{key}/activate (spec §2, decisions D1–D3)."""
from __future__ import annotations

import pytest

from app.auth import permissions as PM


def test_the_settings_read_reports_the_flag_as_read_only_and_names_where_it_is_set(staff_client):
    body = staff_client.get("/api/admin/settings").json()
    assert body["market_data_public"]["writable"] is False
    assert body["market_data_public"]["set_in"] == "Railway environment variable MARKET_DATA_PUBLIC"
    assert isinstance(body["market_data_public"]["value"], bool)


def test_the_settings_read_reports_every_registered_dataset_s_vintage(staff_client, registry_with_a_newer_load):
    rows = {v["dataset_key"]: v for v in staff_client.get("/api/admin/settings").json()["vintages"]}
    row = rows[registry_with_a_newer_load.dataset_key]
    assert row["active_vintage"] == registry_with_a_newer_load.active
    assert row["loaded_vintage"] == registry_with_a_newer_load.loaded
    assert row["activatable"] is True


def test_a_dataset_whose_newest_succeeded_load_is_already_active_is_not_activatable(staff_client, registry_already_active):
    rows = {v["dataset_key"]: v for v in staff_client.get("/api/admin/settings").json()["vintages"]}
    assert rows[registry_already_active.dataset_key]["activatable"] is False


def test_the_settings_read_reports_the_sign_up_counts_and_the_last_send(staff_client, two_signups_one_mailed):
    signups = staff_client.get("/api/admin/settings").json()["signups"]
    assert (signups["total"], signups["launch_mailed"], signups["not_mailed"]) == (2, 1, 1)
    assert signups["last_mailed_at"] is not None


def test_a_buyer_cannot_read_the_settings(buyer_client):
    assert buyer_client.get("/api/admin/settings").status_code == 403


def test_the_three_permissions_the_aggregate_read_serves_have_the_same_holders():
    """Decision D3. `GET /api/admin/settings` is guarded by `data_sources.read` alone and serves
    facts that belong to `signups.read` and to the screen's own `page.admin`. Today all three are
    staff|admin. The day one of them moves, this fails — rather than one row's facts leaking to
    the holder of another row's permission."""
    assert PM.MATRIX["data_sources.read"] == PM.MATRIX["signups.read"] == PM.MATRIX["page.admin"]


def test_activating_a_vintage_writes_active_vintage_and_one_audit_row(admin_reauthed_client, registry_with_a_newer_load, audit_rows):
    r = admin_reauthed_client.post(
        f"/api/admin/vintages/{registry_with_a_newer_load.dataset_key}/activate",
        json={"vintage": registry_with_a_newer_load.loaded},
    )
    assert r.status_code == 200, r.text
    assert r.json()["vintage"] == registry_with_a_newer_load.loaded
    assert r.json()["prior_vintage"] == registry_with_a_newer_load.active
    written = [a for a in audit_rows() if a["action"] == "engine.activate"]
    assert len(written) == 1 and written[0]["target_id"] == registry_with_a_newer_load.dataset_key


def test_an_unknown_dataset_key_is_refused_before_anything_is_read(admin_reauthed_client):
    r = admin_reauthed_client.post("/api/admin/vintages/not-a-dataset/activate", json={"vintage": "2023"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_DATASET"


def test_a_forced_activation_without_a_note_is_refused(admin_reauthed_client, registry_with_a_newer_load):
    r = admin_reauthed_client.post(
        f"/api/admin/vintages/{registry_with_a_newer_load.dataset_key}/activate",
        json={"vintage": registry_with_a_newer_load.loaded, "force": True},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "NOTE_REQUIRED"


def test_an_activation_the_qa_gate_refuses_is_a_409_naming_the_reason(admin_reauthed_client, registry_with_a_failed_load):
    r = admin_reauthed_client.post(
        f"/api/admin/vintages/{registry_with_a_failed_load.dataset_key}/activate",
        json={"vintage": registry_with_a_failed_load.loaded},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == "ACTIVATION_REFUSED"
    assert "succeeded" in r.json()["error"]["message"]


def test_an_admin_without_a_fresh_password_is_refused(admin_client, registry_with_a_newer_load):
    r = admin_client.post(
        f"/api/admin/vintages/{registry_with_a_newer_load.dataset_key}/activate",
        json={"vintage": registry_with_a_newer_load.loaded},
    )
    assert r.status_code == 401 and r.json()["error"]["code"] == "REAUTH_REQUIRED"


def test_an_api_token_can_never_activate_a_vintage(admin_token_client, registry_with_a_newer_load):
    r = admin_token_client.post(
        f"/api/admin/vintages/{registry_with_a_newer_load.dataset_key}/activate",
        json={"vintage": registry_with_a_newer_load.loaded},
    )
    assert r.status_code == 401 and r.json()["error"]["code"] == "REAUTH_TOKEN"


@pytest.mark.parametrize("client_name", ["staff_reauthed_client", "buyer_client"])
def test_only_an_admin_may_activate(request, client_name, registry_with_a_newer_load):
    client = request.getfixturevalue(client_name)
    r = client.post(f"/api/admin/vintages/{registry_with_a_newer_load.dataset_key}/activate",
                    json={"vintage": registry_with_a_newer_load.loaded})
    assert r.status_code == 403


def test_a_legacy_operator_activation_records_the_operator_rather_than_an_account(legacy_client, registry_with_a_newer_load, audit_rows):
    """`deps.require` exempts `kind == "legacy"` from the re-auth window and the operator secret
    names no `account` row, so `by` falls back to the literal "operator" — the one branch in this
    handler that is not an account email."""
    r = legacy_client.post(f"/api/admin/vintages/{registry_with_a_newer_load.dataset_key}/activate",
                           json={"vintage": registry_with_a_newer_load.loaded})
    assert r.status_code == 200
    assert [a for a in audit_rows() if a["action"] == "engine.activate"][0]["actor_role"] == "legacy:operator"
```

Add the four fixtures to `tests/api/conftest.py` beside the existing client fixtures (`staff_client`, `buyer_client`, `admin_client`, `admin_reauthed_client`, `admin_token_client`, `legacy_client`, `audit_rows` already exist there — check with `grep -n "def staff_client\|def admin_reauthed_client\|def audit_rows" tests/api/conftest.py` and reuse; only the three registry fixtures and `two_signups_one_mailed` are new):

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RegistryState:
    dataset_key: str
    active: str | None
    loaded: str | None


@pytest.fixture
def registry_with_a_newer_load(db_conn) -> RegistryState:
    """`acs5` active on one vintage with a SUCCEEDED load of a newer one — the state the Settings
    row's "Activate <vintage>" button exists for. Row counts are seeded equal, so `vintage.qa`'s
    [0.8, 1.25] ratio gate passes without `force`."""
    return _seed_registry(db_conn, "acs5", active="2018–2022", loaded="2019–2023", status="succeeded")


@pytest.fixture
def registry_already_active(db_conn) -> RegistryState:
    return _seed_registry(db_conn, "acs5", active="2019–2023", loaded="2019–2023", status="succeeded")


@pytest.fixture
def registry_with_a_failed_load(db_conn) -> RegistryState:
    return _seed_registry(db_conn, "acs5", active="2018–2022", loaded="2019–2023", status="failed")


@pytest.fixture
def two_signups_one_mailed(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO interest_signup (email, email_normalised, consent_version, source)"
                    " VALUES ('a@example.org','a@example.org','coming-soon-v1','coming-soon'),"
                    "        ('b@example.org','b@example.org','coming-soon-v1','coming-soon')")
        cur.execute("UPDATE interest_signup SET launch_mailed_at = now() WHERE email_normalised = 'a@example.org'")
    db_conn.commit()
```

`_seed_registry` is a module-level helper in the same conftest — it inserts a `dataset_registry` row if absent, an `ingest_run` with the given `status` and `finished_at = now()`, `acs_measure` rows for both vintages so `vintage._count` returns a ratio of 1.0, and an `active_vintage` row. Write it to mirror `tests/census/conftest.py`'s own registry seeding (`grep -n "dataset_registry" tests/census/conftest.py` — reuse that helper by import if it is already exported rather than writing a second one).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `poetry run pytest tests/api/test_admin_settings.py -q`
Expected: every case FAILS with `assert 404 == 200` (the router is not mounted) or, on the permission pin, PASSES already — `test_the_three_permissions_the_aggregate_read_serves_have_the_same_holders` is a characterisation of today's matrix and is green from the start. That is correct: it is a drift detector, not a driver.

- [ ] **Step 3: Write `app/api/admin_settings.py`**

```python
"""The Admin > Settings surface (admin control surface spec §2) — the settings-shaped writes that
existed as scattered admin actions with no screen, and the one read behind them.

Three rows today (family A41); a fourth, api tokens, arrives with A46.

* **Market data visible to anonymous visitors is READ-ONLY here, and deliberately** (controller
  decision D1, 2026-09-14). `MARKET_DATA_PUBLIC` is a Railway environment variable
  (`app/config.py`), no route has ever written it, and `scripts/verify-deploy.sh` refuses a
  production deploy where it is true. A button that cannot complete is not drawn (spec §1 rule 3),
  so this row reports the value and says where it is set.
* **Census data vintage is the one NEW write.** `engine.activate` has been a permission with no
  HTTP route since Task I5, reachable only from `scripts/census_load.py activate`. The route below
  delegates to `app.census.vintage.activate` — the CLI's own function, with its own QA gate — so
  there is ONE activation path and not two.
* **Launch mail to sign-ups** reports the counts; the SEND is `admin_signups`'s own
  `POST /api/admin/signups/launch-mail` and is not duplicated here.

Guarded by `data_sources.read`, and `tests/api/test_admin_settings.py` pins
`MATRIX["data_sources.read"] == MATRIX["signups.read"] == MATRIX["page.admin"]` so the day those
three diverge this aggregate read fails loudly instead of serving one row's facts to the holder of
another row's permission (decision D3).

Two shapes `app/api/admin_users.py` documents are load-bearing here too: every guard is a
module-level constant, never wrapped (`tests/auth/test_permissions.py` resolves a route's
permission by the guard's object IDENTITY), and `audit.write(` is called in the audited endpoint's
OWN body (the drift test reads `inspect.getsource(route.endpoint)`).
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import audit
from app.auth import sessions as S
from app.auth.deps import require
from app.census import vintage as V
from app.config import settings
from app.db import sync_conn

router = APIRouter(prefix="/api/admin")

REQUIRE_SETTINGS_READ = require("data_sources.read")
REQUIRE_ACTIVATE = require("engine.activate")
Activator = Annotated[S.Principal, Depends(REQUIRE_ACTIVATE)]

MAX_NOTE = 4_000
#: Where `MARKET_DATA_PUBLIC` is really set — stated, not guessed: it is a Railway environment
#: variable, per service per environment (CLAUDE.md), and this row exists to tell a reader that.
MARKET_FLAG_SOURCE = "Railway environment variable MARKET_DATA_PUBLIC"

VINTAGE_SQL = """
SELECT r.dataset_key, r.display_name,
       a.vintage, a.activated_at, a.activated_by, a.note,
       (SELECT i.vintage FROM ingest_run i
         WHERE i.dataset_key = r.dataset_key AND i.status = 'succeeded'
         ORDER BY i.id DESC LIMIT 1),
       (SELECT i.finished_at FROM ingest_run i
         WHERE i.dataset_key = r.dataset_key AND i.status = 'succeeded'
         ORDER BY i.id DESC LIMIT 1)
  FROM dataset_registry r LEFT JOIN active_vintage a USING (dataset_key)
 ORDER BY r.dataset_key
"""

SIGNUP_SQL = """
SELECT count(*), count(*) FILTER (WHERE launch_mailed_at IS NOT NULL), max(launch_mailed_at)
  FROM interest_signup
"""


def _error(code: str, message: str, status: int) -> JSONResponse:
    """Decision A5's body, the shape `app/api/admin_data_sources.py` uses."""
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _vintage_row(r: tuple[Any, ...]) -> dict[str, Any]:
    """One dataset's vintage facts.

    `activatable` is exactly the spec's "only when a newer load exists": a SUCCEEDED load whose
    vintage is not the one already active. It is a hint for the screen and never the gate — the
    route re-asks `vintage.qa` on the way in, so a stale tab cannot force an activation this flag
    would have hidden."""
    loaded = r[6]
    return {"dataset_key": r[0], "display_name": r[1], "active_vintage": r[2],
            "activated_at": _iso(r[3]), "activated_by": r[4], "activation_note": r[5],
            "loaded_vintage": loaded, "last_load_finished_at": _iso(r[7]),
            "activatable": loaded is not None and loaded != r[2]}


@router.get("/settings", dependencies=[Depends(REQUIRE_SETTINGS_READ)])
def read_settings() -> dict[str, Any]:
    """The three Settings rows' live facts.

    A plain `def`, so FastAPI runs it in its threadpool (`admin_data_sources.list_data_sources`'s
    own rule): everything below it is blocking psycopg2, and on the event loop that would park
    every other request for the duration.

    NOT audited: `data_sources.read` is not in `permissions.AUDITED`, and one row per poll of a
    settings screen into a table whose triggers refuse DELETE is the leak `users.review` was split
    out to avoid."""
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute(VINTAGE_SQL)
        vintages = [_vintage_row(row) for row in cur.fetchall()]
        cur.execute(SIGNUP_SQL)
        total, mailed, last = cast("tuple[int, int, datetime | None]", cur.fetchone())
    return {
        "market_data_public": {"value": settings.market_data_public, "environment": settings.environment,
                               "set_in": MARKET_FLAG_SOURCE, "writable": False},
        "vintages": vintages,
        "signups": {"total": total, "launch_mailed": mailed, "not_mailed": total - mailed,
                    "last_mailed_at": _iso(last), "sendable": settings.site_mode == "app"},
    }


class ActivationIn(BaseModel):
    vintage: str = Field(max_length=64)
    force: bool = False
    note: str | None = Field(default=None, max_length=MAX_NOTE)


@router.post("/vintages/{dataset_key}/activate")
def activate_vintage(dataset_key: str, body: ActivationIn, request: Request, principal: Activator) -> JSONResponse:
    """Flip `active_vintage` for one dataset — the CLI's own `app.census.vintage.activate`, reached
    from a screen.

    A plain `def` for `read_settings`' reason, and more so: this takes a row lock across the QA
    counts and the upsert.

    `engine.activate` is admin-only, in `permissions.REAUTH` (the caller confirmed their password
    within ten minutes, and no api token can reach it at all — `deps.TokenCannotReauth`) and in
    `permissions.AUDITED`, so `audit.write(` is called HERE and never through a helper.

    A forced activation requires a note for the reason `scripts/census_load.py`'s argparse requires
    one: a row-count ratio outside [0.8, 1.25] overridden with no recorded why is precisely what
    that gate exists to prevent."""
    if dataset_key not in V.TABLE_FOR:
        return _error("BAD_DATASET", f"dataset_key must be one of {', '.join(sorted(V.TABLE_FOR))}.", 422)
    if body.force and not (body.note or "").strip():
        return _error("NOTE_REQUIRED", "A forced activation must record why.", 422)
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute("SELECT email FROM account WHERE id=%s", (principal.account_id,))
            found = cur.fetchone()
        # `deps.require` exempts a legacy operator from the re-auth window and that principal names
        # no `account` row (`deps.LEGACY_ADMIN` is synthetic), so `activated_by` says so rather than
        # carrying a uuid nobody can resolve.
        by = cast("tuple[str]", found)[0] if found is not None else "operator"
        try:
            report = V.activate(conn, dataset_key, body.vintage, by, force=body.force, note=body.note)
        except V.ActivationRefused as exc:
            return _error("ACTIVATION_REFUSED", str(exc), 409)
        audit.write(conn, actor=principal, action="engine.activate", target_type="dataset",
                    target_id=dataset_key, before={"vintage": report.prior_vintage},
                    after={"vintage": body.vintage, "force": body.force}, reason=body.note, request=request)
    return JSONResponse({"dataset_key": dataset_key, "vintage": body.vintage,
                         "prior_vintage": report.prior_vintage, "rows": report.rows_new,
                         "ratio": report.ratio, "note": body.note})
```

- [ ] **Step 4: Mount the router**

In `app/main.py`, immediately after `app.include_router(admin_data_sources_router)` (line 136) and inside the same `site_mode == "app"` block:

```python
        # Same gate, same reason (decision D2, 2026-09-14): Settings reads the registry and the
        # sign-up counts and its one write flips `active_vintage` — staff/admin and
        # admin-and-re-authenticated respectively, so behind the Coming Soon page it is absent
        # rather than merely guarded, like every other /api/admin/* path.
        app.include_router(admin_settings_router)
```

with the import beside the other admin routers at the top of `create_app`'s import block:

```python
    from app.api.admin_settings import router as admin_settings_router
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `poetry run pytest tests/api/test_admin_settings.py tests/auth/test_permissions.py -q`
Expected: PASS. `tests/auth/test_permissions.py::test_every_route_is_guarded_or_public` must pass unchanged — both new routes carry a module-level `require(...)`, so neither needs a `PUBLIC_ROUTES` entry.

- [ ] **Step 6: Document the two routes**

Append to `docs/integrations/market-data-api.md`, in the shape its `GET /api/admin/data-sources` section already uses (path, permission, a real sample body). `tests/api/test_contract_doc.py` compares the documented samples against what the routers serve; run it and fix the doc, never the router.

- [ ] **Step 7: Run the whole backend gate**

```bash
docker compose -f docker-compose.dev.yml up -d
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m "not timing"
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m timing -p no:randomly --cov-append --cov-report=xml --cov-fail-under=100
```
Expected: PASS, 100 %.

- [ ] **Step 8: Commit**

```bash
git add app/api/admin_settings.py app/main.py tests/api/test_admin_settings.py tests/api/conftest.py docs/integrations/market-data-api.md
git commit -m "feat(admin): the settings read, and engine.activate gains the route it never had

GET /api/admin/settings serves the three Settings rows' live facts and
POST /api/admin/vintages/{key}/activate delegates to the CLI's own
app.census.vintage.activate, so there is one activation path and not two.
MARKET_DATA_PUBLIC is reported read-only: it is a Railway environment
variable and verify-deploy refuses it on production, so no button is drawn
for it (spec §1 rule 3, decision D1).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 2: `admin/settings.ts` and `admin/reauth.ts` (A41, frontend adapters)

The M6 pattern a third and fourth time: a pure mapping from the API payload to the rows the design's own table template already renders, plus the one-method adapter the dialog calls. **No design file changes in this task** — the adapters exist before the tab that uses them, so the tab's task is a pure design diff a reviewer can read on its own.

**Re-basing states: NONE.** **The thirteen frozen hashes must not move.**

**Files:**
- Create: `frontend/src/admin/settings.ts`, `frontend/src/admin/settings.test.ts`
- Create: `frontend/src/admin/reauth.ts`, `frontend/src/admin/reauth.test.ts`
- Modify: `frontend/src/app.setup.js` (two new app-only props, beside `adminListings` at `:104`)

**Interfaces:**
- Consumes: Task 1's `GET /api/admin/settings` and `POST /api/admin/vintages/{key}/activate`; `frontend/src/admin/users.ts`'s `cell(main, sub, pill, pillTone, actions)`, `A(label, tone, go)`, `type Cell`, `type ActionButton` (all exported today, all copied verbatim from `logic.js`'s `adminVals()`); `frontend/src/auth/api.ts`'s `reauth(password): Promise<Status>` and `csrfToken()`.
- Produces:
  ```ts
  // frontend/src/admin/settings.ts
  export interface FlagFacts { value: boolean; environment: string; set_in: string; writable: boolean }
  export interface VintageFacts {
    dataset_key: string; display_name: string;
    active_vintage: string | null; activated_at: string | null; activated_by: string | null;
    activation_note: string | null; loaded_vintage: string | null;
    last_load_finished_at: string | null; activatable: boolean;
  }
  export interface SignupFacts {
    total: number; launch_mailed: number; not_mailed: number;
    last_mailed_at: string | null; sendable: boolean;
  }
  export interface SettingsPayload { market_data_public: FlagFacts; vintages: VintageFacts[]; signups: SignupFacts }
  /** THE ONE step-up signature, used unchanged by Tasks 6, 11, 14, 16, 18 and 19. Four arguments
   *  from the start, so no later family widens it: `note` is `null` where the action needs no note
   *  and `{label, placeholder}` where it does (A42 is the only caller that passes one today). */
  export interface StepUp {
    stepUp(perm: string, label: string, run: (note: string) => Promise<void>,
           note: { label: string; placeholder: string } | null): Promise<void>;
    refuse(message: string): void;
  }
  export type SettingsUi = StepUp;
  export const SETTINGS_COLUMNS: readonly string[];   // ['Setting', 'Value and provenance', 'Status', 'Action']
  export const SETTINGS_GRID: string;                 // '1.1fr 1.6fr .8fr .9fr' — the Data Sources tab's own grid
  export const SETTINGS_FOOTNOTE: string;
  export function toSettingsRows(payload: SettingsPayload, ui: SettingsUi,
                                 activate: (key: string, vintage: string) => Promise<void>,
                                 send: () => Promise<void>): Cell[][];
  export interface AdminSettingsAdapter { list(): Promise<Cell[][]> }
  export function makeAdminSettingsAdapter(ui?: SettingsUi): AdminSettingsAdapter;

  // frontend/src/admin/reauth.ts
  export interface ReauthAdapter { confirm(password: string): Promise<void> }
  export function makeReauthAdapter(): ReauthAdapter;   // rejects with Error(<the server's own message>)
  ```
  **Task 3 reads `SETTINGS_COLUMNS`, `SETTINGS_GRID`, `SETTINGS_FOOTNOTE` and `AdminSettingsAdapter.list()`. Task 4 reads `ReauthAdapter.confirm`. Task 19 adds a FIFTH parameter, `tokenSubline: string`, and the two A46 rows it gates — RED first, in its own cycle. Do not write that parameter here: an unreachable arm cannot be covered, and the 100 %-branch gate would reject it.**

- [ ] **Step 1: Write the failing tests**

`frontend/src/admin/settings.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { SETTINGS_GRID, makeAdminSettingsAdapter, toSettingsRows, type SettingsPayload, type SettingsUi } from './settings';

const PAYLOAD: SettingsPayload = {
  market_data_public: { value: false, environment: 'qa', set_in: 'Railway environment variable MARKET_DATA_PUBLIC', writable: false },
  vintages: [
    { dataset_key: 'acs5', display_name: 'ACS 5-year estimates', active_vintage: '2018–2022',
      activated_at: '2026-06-02T00:00:00Z', activated_by: 'ops@vin.test', activation_note: null,
      loaded_vintage: '2019–2023', last_load_finished_at: '2026-09-01T00:00:00Z', activatable: true },
    { dataset_key: 'tiger_cb', display_name: 'TIGER cartographic boundaries', active_vintage: '2023',
      activated_at: null, activated_by: null, activation_note: null,
      loaded_vintage: '2023', last_load_finished_at: '2026-05-04T00:00:00Z', activatable: false }
  ],
  signups: { total: 12, launch_mailed: 0, not_mailed: 12, last_mailed_at: null, sendable: true }
};

const ui = (): SettingsUi & { calls: string[] } => {
  const calls: string[] = [];
  return { calls,
    stepUp: async (perm, label, run, note) => { calls.push(`stepUp:${perm}:${label}:${note ? 'note' : 'no-note'}`); await run(''); },
    refuse: (m) => { calls.push(`refuse:${m}`); } };
};

describe('toSettingsRows', () => {
  it('draws NO action for the market-data flag, and says where it is really set', () => {
    const [flag] = toSettingsRows(PAYLOAD, ui(), activate, sendMail);
    expect(flag[0].main).toBe('Market data visible to anonymous visitors');
    expect(flag[1].sub).toContain('Railway environment variable MARKET_DATA_PUBLIC');
    expect(flag[2].pill).toBe('Off');
    expect(flag[3].hasActions, 'a flag no route writes must not offer a button (spec §1 rule 3)').toBe(false);
  });

  it('offers Activate only for a dataset whose newest succeeded load is not the active one', () => {
    const rows = toSettingsRows(PAYLOAD, ui(), activate, sendMail);
    const acs = rows.find((r) => r[0].main === 'ACS 5-year estimates')!;
    const tiger = rows.find((r) => r[0].main === 'TIGER cartographic boundaries')!;
    expect(acs[3].actions.map((a) => a.label)).toEqual(['Activate 2019–2023']);
    expect(tiger[3].hasActions).toBe(false);
    expect(tiger[2].pill).toBe('Active');
  });

  it('names who activated the live vintage and when, and says so when nobody has', () => {
    const rows = toSettingsRows(PAYLOAD, ui(), activate, sendMail);
    expect(rows.find((r) => r[0].main === 'ACS 5-year estimates')![1].sub)
      .toBe('Active 2018–2022 · activated June 2026 by ops@vin.test · loaded 2019–2023 September 2026');
    expect(rows.find((r) => r[0].main === 'TIGER cartographic boundaries')![1].sub)
      .toBe('Active 2023 · never activated from a screen · loaded 2023 May 2026');
  });

  it('reports the launch mail as not sent, and offers Send through a step-up', async () => {
    const u = ui();
    const rows = toSettingsRows(PAYLOAD, u, activate, sendMail);
    const mail = rows.find((r) => r[0].main === 'Launch mail to sign-ups')!;
    expect(mail[1].sub).toBe('12 sign-ups · 12 not yet mailed');
    expect(mail[2].pill).toBe('Not sent');
    await mail[3].actions[0].go();
    expect(u.calls[0]).toBe('stepUp:signups.notify:Send the launch mail:no-note');
  });

  it('drops the Send button where the site is not open yet — the API would answer 409', () => {
    const closed = { ...PAYLOAD, signups: { ...PAYLOAD.signups, sendable: false } };
    expect(toSettingsRows(closed, ui(), activate, sendMail).find((r) => r[0].main === 'Launch mail to sign-ups')![3].hasActions).toBe(false);
  });

  it('reports a launch mail that HAS been sent with its date', () => {
    const sent = { ...PAYLOAD, signups: { ...PAYLOAD.signups, launch_mailed: 12, not_mailed: 0, last_mailed_at: '2026-09-10T00:00:00Z' } };
    const mail = toSettingsRows(sent, ui(), activate, sendMail).find((r) => r[0].main === 'Launch mail to sign-ups')!;
    expect(mail[2].pill).toBe('Sent September 2026');
    expect(mail[3].hasActions, 'nothing is left to mail').toBe(false);
  });

  it('uses the Data Sources tab’s own grid, so the fifth tab invents no column width', () => {
    expect(SETTINGS_GRID).toBe('1.1fr 1.6fr .8fr .9fr');
  });
});

describe('makeAdminSettingsAdapter', () => {
  it('GETs /api/admin/settings and maps it', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(PAYLOAD), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const rows = await makeAdminSettingsAdapter(ui()).list();
    expect(fetchMock.mock.calls[0][0]).toBe('/api/admin/settings');
    expect(rows).toHaveLength(4);   // flag + two datasets + launch mail
  });

  it('throws rather than answering rows when the read is refused', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 403 })));
    await expect(makeAdminSettingsAdapter(ui()).list()).rejects.toThrow('the settings could not be read');
  });

  it('activates through the step-up and re-reads nothing the caller did not ask for', async () => {
    const u = ui();
    const fetchMock = vi.fn(async (url: string) =>
      url === '/api/admin/settings' ? new Response(JSON.stringify(PAYLOAD), { status: 200 })
                                    : new Response(JSON.stringify({ vintage: '2019–2023' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const rows = await makeAdminSettingsAdapter(u).list();
    await rows.find((r) => r[0].main === 'ACS 5-year estimates')![3].actions[0].go();
    expect(u.calls).toEqual(['stepUp:engine.activate:Activate 2019–2023:no-note']);
    expect(fetchMock.mock.calls[1][0]).toBe('/api/admin/vintages/acs5/activate');
  });

  it('shows the server’s own refusal when an activation is rejected', async () => {
    const u = ui();
    const fetchMock = vi.fn(async (url: string) =>
      url === '/api/admin/settings' ? new Response(JSON.stringify(PAYLOAD), { status: 200 })
        : new Response(JSON.stringify({ error: { code: 'ACTIVATION_REFUSED', message: 'row count ratio 0.41 …' } }), { status: 409 }));
    vi.stubGlobal('fetch', fetchMock);
    const rows = await makeAdminSettingsAdapter(u).list();
    await rows.find((r) => r[0].main === 'ACS 5-year estimates')![3].actions[0].go();
    expect(u.calls).toEqual(['stepUp:engine.activate:Activate 2019–2023:no-note', 'refuse:row count ratio 0.41 …']);
  });
});
```

`frontend/src/admin/reauth.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { makeReauthAdapter } from './reauth';

describe('makeReauthAdapter', () => {
  it('POSTs the password to /api/auth/reauth with the CSRF header', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ status: 'reauthenticated' }), { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    Object.defineProperty(document, 'cookie', { value: 'pm_csrf=abc', configurable: true });
    await makeReauthAdapter().confirm('a password');
    expect(fetchMock.mock.calls[0][0]).toBe('/api/auth/reauth');
    expect((fetchMock.mock.calls[0][1] as RequestInit).headers).toMatchObject({ 'X-CSRF-Token': 'abc' });
  });

  it('rejects with the server’s own message on a wrong password', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ error: { code: 'BAD_PASSWORD', message: 'That password is not right.' } }), { status: 401 })));
    await expect(makeReauthAdapter().confirm('wrong')).rejects.toThrow('That password is not right.');
  });

  it('rejects with a plain sentence when the refusal carries no message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('not json', { status: 500 })));
    await expect(makeReauthAdapter().confirm('x')).rejects.toThrow('That password could not be confirmed.');
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/admin/settings.test.ts src/admin/reauth.test.ts`
Expected: FAIL — `Failed to resolve import "./settings"` and `"./reauth"`.

- [ ] **Step 3: Write `frontend/src/admin/reauth.ts`**

```ts
/**
 * The prototype's `reauth` adapter — one method, because the DIALOG is the design's (A41.5–A41.11)
 * and this is only the credential going to the server.
 *
 * `permissions.REAUTH` names six actions (`licence.decide`, `engine.activate`, `roles.grant`,
 * `tokens.manage`, `users.revoke`, `signups.notify`); `deps.require` refuses each of them unless
 * `session.reauth_at` is inside ten minutes, and an api token can never satisfy it at all. This is
 * the one call that stamps it.
 *
 * It lives in its own module, rather than inline in `app.setup.js`, for the reason `auth.ts`
 * records: that file is copied verbatim into `App.vue` by `npm run gen:app` and is therefore
 * outside the coverage gate, so logic written there has no unit tests.
 */
import { csrfToken } from '../auth/api';

export interface ReauthAdapter {
  /** Resolves once the session carries a fresh password confirmation; rejects with the server's
   *  own message so the dialog's `formError` slot renders what the API said, never a guess. */
  confirm(password: string): Promise<void>;
}

export function makeReauthAdapter(): ReauthAdapter {
  return {
    confirm: async (password) => {
      const res = await fetch('/api/auth/reauth', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken() },
        body: JSON.stringify({ password })
      });
      if (res.ok) return;
      const body = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
      throw new Error(body?.error?.message ?? 'That password could not be confirmed.');
    }
  };
}
```

- [ ] **Step 4: Write `frontend/src/admin/settings.ts`**

```ts
/**
 * `GET /api/admin/settings` → the approved design's table, on a fifth tab (admin control surface
 * spec §2).
 *
 * The M6 pattern `frontend/src/admin/users.ts` established and `listings.ts`/`data_sources.ts`
 * repeated: a pure mapping from the API payload to the rows `adminVals()`'s own
 * `set.rows.map((cells, i) => …)` already wraps. `cell()` and `A()` are IMPORTED from
 * `admin/users.ts` here rather than copied a fourth time — this tab has no design fixture of its
 * own to be pinned against, so a fourth independent copy would be pinned against nothing.
 *
 * **The flag row has no button, and that is the point** (controller decision D1, 2026-09-14):
 * `MARKET_DATA_PUBLIC` is a Railway environment variable, no route writes it, and
 * `scripts/verify-deploy.sh` refuses a production deploy where it is true. An action renders only
 * if it completes (spec §1 rule 3).
 *
 * **One row per registered dataset, not one row for "Census data vintage"** (decision D11): each
 * dataset has its own active vintage, its own last load and its own activation, and a single row
 * could offer only one dataset's button. The `Setting` cell carries the dataset's own
 * `display_name`, which is the registry's string and not one composed here.
 */
import { reauth } from '../auth/api';
import { A, cell, type ActionButton, type Cell } from './users';

export interface FlagFacts { value: boolean; environment: string; set_in: string; writable: boolean }
export interface VintageFacts {
  dataset_key: string; display_name: string;
  active_vintage: string | null; activated_at: string | null; activated_by: string | null;
  activation_note: string | null; loaded_vintage: string | null;
  last_load_finished_at: string | null; activatable: boolean;
}
export interface SignupFacts { total: number; launch_mailed: number; not_mailed: number; last_mailed_at: string | null; sendable: boolean }
export interface SettingsPayload { market_data_public: FlagFacts; vintages: VintageFacts[]; signups: SignupFacts }

/**
 * THE step-up shape, declared once and imported by every surface that has a REAUTH action —
 * `admin/data_sources.ts` (A42), `admin/requests.ts` (A43), `admin/user_detail.ts` (A44),
 * `admin/tokens.ts` (A46) and `admin/users.ts`'s restored Revoke (A41). Four arguments from the
 * start, so no later family widens the signature and breaks every caller:
 *
 *   `perm`  — the `permissions.REAUTH` action, for the dialog's own guard and for the label;
 *   `label` — what the member asked for, so the dialog says what it is about to do;
 *   `run`   — the action, issued ONLY after the password is confirmed, and given the note;
 *   `note`  — `null` where the action needs none, `{label, placeholder}` where it does. Today
 *             only `licence.decide` (A42) passes one; `roles.grant` deliberately does not,
 *             because `POST /api/admin/users/{id}/grants` takes no note and a field the route
 *             discards is a lie about what was recorded.
 *
 * `stepUp` resolves when the ACTION completed, not when the password was accepted — spec §1
 * rule 3 applied to the thing that gates the action.
 */
export interface StepUp {
  stepUp(perm: string, label: string, run: (note: string) => Promise<void>,
         note: { label: string; placeholder: string } | null): Promise<void>;
  refuse(message: string): void;
}

export type SettingsUi = StepUp;

export const SETTINGS_COLUMNS: readonly string[] = ['Setting', 'Value and provenance', 'Status', 'Action'];
/** The Data Sources tab's own grid (`logic.js`'s `sets.data.grid`), so the fifth tab invents no column width. */
export const SETTINGS_GRID = '1.1fr 1.6fr .8fr .9fr';
export const SETTINGS_FOOTNOTE =
  'Every change here is recorded with the name of the person who made it. Values set in the deployment environment are shown for reference and cannot be changed from this screen.';

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

/** `Month Year`, UTC — the vocabulary this very tab already uses ("Last checked June 2026") and
 *  never `toLocaleDateString`, whose answer depends on the runner's locale (`admin/listings.ts`'s rule). */
function monthYear(iso: string | null): string | null {
  if (iso === null) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

function flagRow(f: FlagFacts): Cell[] {
  return [
    cell('Market data visible to anonymous visitors', null),
    cell(`${f.value ? 'On' : 'Off'} in ${f.environment}`, `Set in ${f.set_in}`),
    cell(null, null, f.value ? 'On' : 'Off', f.value ? 'ok' : 'mute'),
    cell(null)
  ];
}

function vintageRow(v: VintageFacts, ui: SettingsUi, activate: (key: string, vintage: string) => Promise<void>): Cell[] {
  const activated = monthYear(v.activated_at);
  const provenance = activated !== null && v.activated_by !== null
    ? `activated ${activated} by ${v.activated_by}`
    : 'never activated from a screen';
  const loaded = monthYear(v.last_load_finished_at);
  const sub = [`Active ${v.active_vintage ?? 'none'}`, provenance,
               v.loaded_vintage === null ? 'no succeeded load' : `loaded ${v.loaded_vintage}${loaded === null ? '' : ` ${loaded}`}`].join(' · ');
  const actions: ActionButton[] = v.activatable && v.loaded_vintage !== null
    ? [A(`Activate ${v.loaded_vintage}`, 'primary', () => ui.stepUp('engine.activate', `Activate ${v.loaded_vintage}`, () => activate(v.dataset_key, v.loaded_vintage as string), null))]
    : [];
  return [
    cell(v.display_name, v.dataset_key),
    cell(null, sub),
    cell(null, null, v.active_vintage === null ? 'Not activated' : 'Active', v.active_vintage === null ? 'mute' : 'ok'),
    actions.length ? cell(null, null, null, null, actions) : cell(null)
  ];
}

function mailRow(s: SignupFacts, ui: SettingsUi, send: () => Promise<void>): Cell[] {
  const sent = monthYear(s.last_mailed_at);
  const actions: ActionButton[] = s.sendable && s.not_mailed > 0
    ? [A('Send', 'primary', () => ui.stepUp('signups.notify', 'Send the launch mail', send, null))]
    : [];
  return [
    cell('Launch mail to sign-ups', null),
    cell(null, `${s.total} sign-ups · ${s.not_mailed} not yet mailed`),
    cell(null, null, sent === null ? 'Not sent' : `Sent ${sent}`, sent === null ? 'mute' : 'ok'),
    actions.length ? cell(null, null, null, null, actions) : cell(null)
  ];
}

/** Three kinds of row: the read-only flag, one per registered dataset (decision D11), and the
 *  launch mail. A46 (Task 19) appends a fifth parameter and two more rows; it is deliberately not
 *  written here, because an unreachable arm cannot be covered. */
export function toSettingsRows(payload: SettingsPayload, ui: SettingsUi,
                               activate: (key: string, vintage: string) => Promise<void>,
                               send: () => Promise<void>): Cell[][] {
  return [flagRow(payload.market_data_public),
          ...payload.vintages.map((v) => vintageRow(v, ui, activate)),
          mailRow(payload.signups, ui, send)];
}

export interface AdminSettingsAdapter { list(): Promise<Cell[][]> }

async function send(method: string, path: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (method !== 'GET') headers['X-CSRF-Token'] = (await import('../auth/api')).csrfToken();
  return fetch(`/api/admin${path}`, { method, credentials: 'same-origin', headers,
                                      body: body === undefined ? undefined : JSON.stringify(body) });
}

async function refusalMessage(res: Response, fallback: string): Promise<string> {
  const body = (await res.json().catch(() => null)) as { error?: { message?: string } } | null;
  return body?.error?.message ?? fallback;
}

function windowUi(): SettingsUi {
  // The real `stepUp` is the design's dialog, handed in by `app.setup.js`. This default exists so
  // the adapter is usable from a script with no dialog mounted, and it REFUSES rather than running
  // the action unauthenticated — the API would answer 401 REAUTH_REQUIRED anyway, and a silent
  // attempt reads as a broken button.
  return { stepUp: async () => { window.alert('This action needs your password. Open it from the Settings tab.'); },
           refuse: (m: string) => window.alert(m) };
}

export function makeAdminSettingsAdapter(ui: SettingsUi = windowUi()): AdminSettingsAdapter {
  const activate = async (key: string, vintage: string) => {
    const res = await send('POST', `/vintages/${encodeURIComponent(key)}/activate`, { vintage });
    if (!res.ok) ui.refuse(await refusalMessage(res, 'That vintage could not be activated.'));
  };
  const sendMail = async () => {
    const res = await send('POST', '/signups/launch-mail', { dry_run: false });
    if (!res.ok) ui.refuse(await refusalMessage(res, 'The launch mail could not be sent.'));
  };
  return {
    list: async () => {
      const res = await send('GET', '/settings');
      if (!res.ok) throw new Error('the settings could not be read');
      return toSettingsRows((await res.json()) as SettingsPayload, ui, activate, sendMail);
    }
  };
}

// `reauth` is re-exported so `app.setup.js` — which is outside the coverage gate — imports one
// module for the tab and its step-up rather than reaching into `auth/api` itself.
export { reauth };
```

- [ ] **Step 5: Declare the two props in `app.setup.js`**

Beside `adminListings` (`frontend/src/app.setup.js:104`), in the same shape and with the same "nothing in the template reads this; only `logic.js` does" note:

```js
  // A41 (admin control surface spec §2): the Settings tab's own reader. App-only, like every
  // adapter prop — the reference and the Claude Design preview receive none and keep the design's
  // own fixture path (spec §1 rule 2).
  adminSettings: { type: Object, default: () => makeAdminSettingsAdapter(designStepUp()) },
  // A41 (spec §3): the step-up credential. One method; the DIALOG is the design's own.
  reauth: { type: Object, default: () => makeReauthAdapter() },
```

`designStepUp()` is **not written in this task** — `makeAdminSettingsAdapter()` takes its default `windowUi()` here, and Task 4 replaces it with the dialog seam once the dialog exists. Write `adminSettings: { type: Object, default: () => makeAdminSettingsAdapter() }` now.

- [ ] **Step 6: Run the frontend gate**

```bash
cd frontend && npm run typecheck && npm run build && npm test
```
Expected: PASS at 100 % lines and branches on the two new modules. `frontend/tests/app-generated.test.ts` must still pass — `app.setup.js` declares two new props and declares no design prop it should not, and no design prop has been added, so prop parity is unchanged.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/admin/settings.ts frontend/src/admin/settings.test.ts \
        frontend/src/admin/reauth.ts frontend/src/admin/reauth.test.ts frontend/src/app.setup.js
git commit -m "feat(admin): the Settings tab's reader and the step-up credential

toSettingsRows maps GET /api/admin/settings onto the design's own cell()
rows; the market-data flag draws no button because no route writes it.
makeReauthAdapter is one method — the dialog itself is the design's.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 3: The fifth tab — A41.1–A41.4 (design)

**Re-basing states: NONE** — the tab is not selected in any approved state, and a fifth `<button>` in the tab row DOES move the row's layout, so **measure, do not reason**: the tab row is inside the `admin` screen, which four frozen captures photograph. **This is the one task in A41 where a frozen hash could legitimately move, and it must not.** The tab entry's `count` is `null` (decision D4) and A36.3/A38.3a/A39.3a's `hasCount` `sc-if` unmounts the lozenge, but the BUTTON itself is new pixels on `admin-users`, `admin-listings`, `admin-requests` and `admin-data-sources`.

**Therefore the tab is gated on adapter presence** (`sc-if` on a render value `admin.hasSettings`, true only when `this.props.adminSettings` is there), which is A16.1's own idiom applied to a control rather than to rows: the reference and the Claude Design preview receive no adapter, render four tabs, and the four frozen captures keep their pixels; the app renders five. The approved states for the tab itself are appended in Task 5, captured on the APP target only — `frontend/tests/screens.ts` has no app-only mode, so Task 5 instead hands the reference the tab through the existing oracle stub (`harness.ts` answers `/api/admin/settings`, and `frontend/tests/design-admin-settings.mjs` gives the REFERENCE the same rows as a `?props=` payload) exactly as `design-admin-listings.mjs` does for A17. **Read Task 5's Oracle section before starting this task** — the two are one design decision split across two reviewable diffs.

**Files:**
- Modify: `frontend/tests/design-amendments.ts` (the A41 block, appended last), `frontend/tests/design-amendments.test.ts`, `frontend/src/logic.test.ts`
- Regenerated: the `.dc.html`, `logic.js`, `App.vue`, `pseudo.css`, `app.setup.js`

**Interfaces:**
- Consumes: Task 2's `AdminSettingsAdapter.list(): Promise<Cell[][]>`, `SETTINGS_COLUMNS`, `SETTINGS_GRID`, `SETTINGS_FOOTNOTE`.
- Produces: the design's `adminVals()` gains `sets.settings` and `hasSettings`; `state.adminSettingRows` (undefined until loaded); `loadAdmin()` gains one line. **Task 19 appends two rows to `sets.settings` through `toSettingsRows`, not through a new `sets` key.**

- [ ] **Step 1: Print and count all four anchors**

```bash
cd .worktrees/feat-a41-settings
python3 - <<'PY'
import pathlib
s = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html").read_text(encoding="utf-8")
anchors = {
 "A41.1": '        { key: "data", label: "Data Sources", count: "2" }\n      ].map((t) => ({\n',
 "A41.2": '      }\n    };\n\n    const set = sets[tab] || sets.users;\n',
 "A41.4": '    adminTab: "users", sellerView: "dash",\n',
 "A41.5": '    if (this.props.adminListings) loads.push(this.props.adminListings.list().then((rows) => this.setState({ adminListingRows: rows }), () => this.setState({ adminListingRows: [] })));\n',
}
for k, v in anchors.items():
    print(k, "amended:", s.count(v))
PY
```
Expected: `1` for every one. **A41.5's anchor is A40.3's own output and A41.1's is A36.3's** (A36 rewrites the `users` tab's `count`, not the `data` tab's — re-count after the A36/A38/A39 merge and STOP if either has moved).

- [ ] **Step 2: Write the failing structural test**

In `frontend/tests/design-amendments.test.ts`, extend `AMENDMENT_IDS` with `'A41.1', 'A41.2', 'A41.3', 'A41.4'`, raise the `toHaveLength` count by four, and add:

```ts
describe('A41 — the Settings tab', () => {
  const amended = readFileSync(AMENDED, 'utf8');

  it('adds a fifth tab entry whose count is null, so no lozenge is painted', () => {
    expect(amended).toContain('{ key: "settings", label: "Settings", count: null }');
  });

  it('gates the fifth tab on the adapter, so the four frozen admin captures keep four tabs', () => {
    expect(amended).toContain('shown: !!this.props.adminSettings');
    expect(amended).toContain('].filter((t) => t.shown !== false).map((t) => ({');
  });

  it('renders the loaded settings rows or NO rows, never a fixture (spec §1 rule 2)', () => {
    expect(amended).toContain('rows: s.adminSettingRows !== undefined ? s.adminSettingRows : []');
  });

  it('loads the tab from loadAdmin, with its own rejection arm', () => {
    expect(amended).toContain('if (this.props.adminSettings) loads.push(this.props.adminSettings.list().then((rows) => this.setState({ adminSettingRows: rows }), () => this.setState({ adminSettingRows: [] })));');
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd frontend && npx vitest run tests/design-amendments.test.ts`
Expected: FAIL — `expected '…' to contain '{ key: "settings", label: "Settings", count: null }'`, and the `toHaveLength` case failing with the old count.

- [ ] **Step 4: Write the five entries**

Append to `frontend/tests/design-amendments.ts`, as the last family block, and add `A41_1 … A41_5` to `amendments()`'s returned list in that order with the block comment the file's own convention requires (which entries are CHAINED and on what).

**The family is FOUR entries — A41.1 (the tab row), A41.2 (the fifth `sets` entry), A41.3 (the state key), A41.4 (the `loadAdmin` line) — and no template edit at all.** A41.1 filters the tab array in the SCRIPT, in the design's own `.map()` chain, so the template is untouched: a second `sc-if` nested inside the tab `sc-for` would have been new template structure, and `hasCount`'s own `sc-if` (A36.3/A38.3a/A39.3a) stays exactly as those families wrote it.

```ts
const RULING_A41 = 'implement Admin screens … compose them from V3\'s own elements under your approval (John, 2026-09-13; D-C53)';

// A41.1 — the fifth tab entry. `count: null` (decision D4): Settings is not a queue, and
// A36.3/A38.3a/A39.3a's `hasCount` sc-if unmounts the lozenge for a null. `shown` is the gate that
// keeps the four frozen admin captures on four tabs: the reference receives no adapter.
const A41_1: Amendment = {
  id: 'A41.1', date: '2026-09-14', ruling: RULING_A41,
  find: '        { key: "data", label: "Data Sources", count: "2" }\n'
      + '      ].map((t) => ({\n',
  replace: '        { key: "data", label: "Data Sources", count: "2" },\n'
      + '        { key: "settings", label: "Settings", count: null, shown: !!this.props.adminSettings }\n'
      + '      ].filter((t) => t.shown !== false).map((t) => ({\n',
  count: 1
};

// A41.2 — the fifth `sets` entry. Rows come from the adapter or are EMPTY; there is no fixture,
// because the design has never drawn this tab and inventing four rows for it would be the faked UI
// CLAUDE.md rules out. Columns, grid and footnote are `src/admin/settings.ts`'s own constants,
// pinned across the seam by `frontend/src/logic.test.ts`.
const A41_2: Amendment = {
  id: 'A41.2', date: '2026-09-14', ruling: RULING_A41,
  find: '      }\n    };\n\n    const set = sets[tab] || sets.users;\n',
  replace: '      },\n'
      + '      settings: {\n'
      + '        columns: ["Setting", "Value and provenance", "Status", "Action"],\n'
      + '        grid: "1.1fr 1.6fr .8fr .9fr",\n'
      + '        footnote: "Every change here is recorded with the name of the person who made it. Values set in the deployment environment are shown for reference and cannot be changed from this screen.",\n'
      + '        rows: s.adminSettingRows !== undefined ? s.adminSettingRows : []\n'
      + '      }\n    };\n\n    const set = sets[tab] || sets.users;\n',
  count: 1
};

// A41.3 — the one state key. `adminSettingRows` is `undefined` until a load answers, which is
// exactly what A41.2's ternary reads.
const A41_3: Amendment = {
  id: 'A41.3', date: '2026-09-14', ruling: RULING_A41,
  find: '    adminTab: "users", sellerView: "dash",\n',
  replace: '    adminTab: "users", sellerView: "dash", adminSettingRows: undefined,\n',
  count: 1
};

// A41.4 — one line in A40.3's `loadAdmin()`, the line that family reserved for each tab, with its
// own rejection arm so a refusal leaves the tab EMPTY rather than back on a fixture.
// Consumes A40.3.
const A41_4: Amendment = {
  id: 'A41.4', date: '2026-09-14', ruling: RULING_A41,
  find: '    if (this.props.adminListings) loads.push(this.props.adminListings.list().then((rows) => this.setState({ adminListingRows: rows }), () => this.setState({ adminListingRows: [] })));\n',
  replace: '    if (this.props.adminListings) loads.push(this.props.adminListings.list().then((rows) => this.setState({ adminListingRows: rows }), () => this.setState({ adminListingRows: [] })));\n'
      + '    if (this.props.adminSettings) loads.push(this.props.adminSettings.list().then((rows) => this.setState({ adminSettingRows: rows }), () => this.setState({ adminSettingRows: [] })));\n',
  count: 1
};
```

- [ ] **Step 5: Regenerate and prove byte equality**

```bash
cd frontend && npm run gen:design && npm run gen:logic && npm run gen:app
npx vitest run tests/design-amendments.test.ts tests/app-generated.test.ts
```
`npm run remap:citations` is NOT run here — no ledger row exists yet; Task 5 writes them and runs it.
Expected: PASS, and `gen:design` prints a total four larger than before.

- [ ] **Step 6: Characterise the four entries**

In `frontend/src/logic.test.ts`, `describe('A41 — the Settings tab', …)`, one case each, driving the real `renderVals()`:
- with no `adminSettings` prop, `v.admin.tabs` has FOUR entries and none is labelled `Settings`;
- with an adapter, FIVE, and the fifth's `count` is `null` and its `hasCount` is `false`;
- `sets.settings.rows` is `[]` with an adapter and no loaded rows, and is the loaded rows once `adminSettingRows` is set;
- `loadAdmin()` with `perms.allowed('page.admin')` true and an `adminSettings` adapter calls `list()` exactly once, and a rejected `list()` leaves `adminSettingRows` `[]` rather than `undefined`.

And ONE cross-seam pin, so the design's three constants cannot drift from `src/admin/settings.ts`'s:
```ts
it('the design’s Settings columns, grid and footnote are src/admin/settings.ts’s own', async () => {
  const { SETTINGS_COLUMNS, SETTINGS_GRID, SETTINGS_FOOTNOTE } = await import('./admin/settings');
  const set = renderWith({ adminSettings: stubAdapter() }).admin;
  expect(set.columns).toEqual([...SETTINGS_COLUMNS]);
  expect(set.headStyle).toContain(SETTINGS_GRID);
  expect(set.footnote).toBe(SETTINGS_FOOTNOTE);
});
```

- [ ] **Step 7: Run the frontend gate, then prove the frozen thirteen did not move**

```bash
cd frontend && npm run typecheck && npm run build && npm test
npm run test:visual:baselines && npm run test:e2e
```
Then run **C6 of the closing sequence** (the hash diff against the Preconditions map) with `PRE="$SCRATCH/a41-baselines-before.json"`.

**Expected output: `0 moved` and no `APPENDED` lines.** A moved `admin-*` row means the adapter gate did not hold — stop with NEEDS_CONTEXT and do not re-pin. `frontend/tests/baseline-manifest.json` is untouched by this task.

- [ ] **Step 8: Commit**

```bash
git add frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts \
        frontend/src/logic.test.ts "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
        frontend/src/logic.js frontend/src/App.vue frontend/src/generated/pseudo.css frontend/src/app.setup.js
git commit -m "feat(design): A41.1-A41.4 — the admin shell gains a Settings tab

Gated on adapter presence, so the reference renders four tabs and the four
frozen admin captures keep their pixels; the app renders five and fills
them from GET /api/admin/settings or leaves them empty.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 4: The re-authentication dialog — A41.5–A41.11 (design)

*(Task 3 used A41.1–A41.4; this family therefore runs A41.5 through A41.11 with no gap.)*

Every action in `permissions.REAUTH` needs a way to supply a fresh password. **The API has refused these without one since Task I5; the design has never had the element.** Composed from V3's own parts and nothing else (spec §3): the interest modal's scrim and box at `z-index: 1100` (A19's own layer, above Leaflet's 1000), the sign-in card's `type="password"` input and its `formError` slot, the sign-in card's primary button relabelled **Confirm**, and the docked panel's 38 px close control.

**Re-basing states: NONE while closed** — the dialog is one unmounted `sc-if` and paints nothing, the A19 proof. **The thirteen frozen hashes must not move**; Task 5 appends the one state that opens it.

**Files:** as Task 3, plus `frontend/src/app.setup.js` (the `designStepUp` seam Task 2 deferred).

**Interfaces:**
- Consumes: Task 2's `ReauthAdapter.confirm(password): Promise<void>` and its `StepUp` interface (`stepUp(perm, label, run, note)` / `refuse(message)`) — the dialog is what `stepUp` opens.
- Produces, in the design: state keys `reauthOpen` (`null` | `{ perm, label, note }`), `reauthPw`, `reauthNote`, `reauthErr`, `reauthBusy`; class members **`openReauth(perm, label, run, note)`** — four arguments from the start, matching `StepUp` exactly, so no later family widens the signature — `closeReauth()` and `submitReauth()`; render value `reauth` (`{ open, title, sub, pw, setPw, error, errorText, busy, confirm, cancel }`). **Task 6 (A42) adds the note's FIELD to the same dialog — the render values `hasNote`/`noteLabel`/`notePlaceholder`/`note`/`setNote`, the markup, and the blank-note refusal — and changes no signature. Tasks 11, 14, 16, 18 and 19 call `openReauth` with `note: null` and add nothing.**

- [ ] **Step 1: Print and count the five anchors**

```bash
python3 - <<'PY'
import pathlib
s = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html").read_text(encoding="utf-8")
anchors = {
 "A41.5 (state)":  '    adminTab: "users", sellerView: "dash", adminSettingRows: undefined,\n',
 "A41.6 (members)":'  trackMenuDismiss() {\n',
 "A41.7 (values)": '      admin: this.adminVals(),\n',
 "A41.8 (markup)": '  <sc-if value="{{ lightbox.open }}" hint-placeholder-val="{{ false }}">\n',
 "A41.9 (keydown)":'    const key = (e) => {\n      if (this.state.lightbox) {\n',
 "A41.10 (outside)":'    const out = (e) => {\n',
 "A41.11 (mount)":  '  componentDidMount() {\n',
}
for k, v in anchors.items():
    print(k, s.count(v))
PY
```
Expected: `1` for every one. **A41.5's anchor is Task 3's own A41.3 output** (CHAINED, so A41.5's ledger row carries `Consumes A41.3`); the other four are pristine or earlier families' and are counted the same way.

- [ ] **Step 2: Write the failing structural test**

```ts
describe('A41 — the re-authentication dialog', () => {
  const amended = readFileSync(AMENDED, 'utf8');

  it('reuses the interest modal’s scrim and box, at A19’s own layer', () => {
    expect(amended).toContain('position: fixed; inset: 0; z-index: 1100; background: rgba(0,58,112,.55); display: grid; place-items: center; padding: 24px;');
    expect(amended).toContain('width: 100%; max-width: 520px; background: var(--color-white); border-radius: 12px; box-shadow: var(--shadow-xl);');
  });

  it('reuses the sign-in card’s password input and its error slot, byte for byte', () => {
    const field = 'height: 44px; padding: 0 13px; font-size: 15px; color: var(--color-navy); background: var(--color-white); border: 1px solid var(--border-subtle); border-radius: 6px; outline: none;';
    expect(amended.split(field).length - 1, 'the dialog adds exactly one more of the sign-in field').toBeGreaterThanOrEqual(7);
    expect(amended).toContain('{{ reauth.errorText }}');
  });

  it('states the one new sentence and no other new copy', () => {
    expect(amended).toContain('Confirm your password to continue');
  });

  it('is closed by Escape through the shared keydown closure, adding no listener', () => {
    expect(amended).toContain('if (this.state.reauthOpen) {\n        if (e.key === "Escape")');
    expect(amended.match(/document\.addEventListener\("keydown"/g) ?? []).toHaveLength(1);
  });

  it('never re-issues the action when the password is refused', () => {
    expect(amended).toContain('this.setState({ reauthErr: (e && e.message) || "That password could not be confirmed.", reauthBusy: false })');
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd frontend && npx vitest run tests/design-amendments.test.ts -t 're-authentication'`
Expected: FAIL on the first `toContain`.

- [ ] **Step 4: Write the seven entries**

Ids **A41.5** (state keys), **A41.6** (the three class members), **A41.7** (the render value), **A41.8** (the markup at the root), **A41.9** (the Escape branch inside A14.5/A19.9's shared `key` closure), **A41.10** (the outside-click branch inside A13.8/A19.10's shared `out` closure), **A41.11** (`go()` and `signOut` clear it, A19.12's own shape). Write them in that order and append them to `amendments()` in that order.

The load-bearing bodies, in full:

```ts
// A41.6 — the three class members, inserted immediately above `trackMenuDismiss()`.
// `openReauth` holds the pending action as a closure in state, which is how the dialog can be one
// element for all six REAUTH actions rather than one dialog per caller. `submitReauth` awaits the
// credential and THEN the action, and closes only when the action itself resolved — spec §1
// rule 3, "an action renders only if it completes", applied to the dialog that gates it.
  openReauth(perm, label, run, note) {
    this.setState({ reauthOpen: { perm: perm, label: label, note: note || null },
                    reauthPw: "", reauthNote: "", reauthErr: "", reauthBusy: false });
    this._reauthRun = run;
  }

  closeReauth() {
    this._reauthRun = null;
    this.setState({ reauthOpen: null, reauthPw: "", reauthNote: "", reauthErr: "", reauthBusy: false });
  }

  submitReauth() {
    const s = this.state;
    if (!s.reauthPw) return this.setState({ reauthErr: "Enter your password." });
    if (!this.props.reauth) return this.closeReauth();
    const run = this._reauthRun;
    const note = s.reauthNote;
    this.setState({ reauthBusy: true, reauthErr: "" });
    return this.props.reauth.confirm(s.reauthPw).then(
      () => (run ? run(note) : null),
      (e) => { this.setState({ reauthErr: (e && e.message) || "That password could not be confirmed.", reauthBusy: false }); throw e; }
    ).then(() => this.closeReauth(), () => {});
  }
```

```ts
// A41.7 — the render value, beside `admin:`. `title`/`sub` are the sign-in card's own sentence
// pattern; `label` is the action the member asked for, so the dialog says what it is about to do.
      reauth: {
        open: !!s.reauthOpen,
        title: "Confirm your password",
        sub: "Confirm your password to continue" + (s.reauthOpen && s.reauthOpen.label ? " — " + s.reauthOpen.label + "." : "."),
        pw: s.reauthPw,
        setPw: (e) => this.setState({ reauthPw: e.target.value, reauthErr: "" }),
        error: !!s.reauthErr,
        errorText: s.reauthErr,
        busy: s.reauthBusy,
        confirm: () => this.submitReauth(),
        cancel: () => this.closeReauth()
      },
```

```ts
// A41.9 — the Escape branch, FIRST inside the shared keydown closure and returning, so the
// lightbox's own branch below is unchanged (A14.4's placement rule: a new branch goes where it
// cannot alter an existing one, and a characterisation case proves the lightbox still steps).
      if (this.state.reauthOpen) {
        if (e.key === "Escape") { e.preventDefault(); this.closeReauth(); }
        return;
      }
```

A41.8's markup is the interest modal's own scrim and box with the sign-in card's field inside it. Compose it by COPYING the two declarations Step 2's test pins (the scrim at `z-index: 1100` and the box) and the password `<label>`/`<input>`/error trio from the sign-in card, and by copying the docked panel's 38 px close button (`aria-label="Close panel"` → `aria-label="Cancel"`). Extract each one first:

```bash
python3 - <<'PY'
import pathlib, re
s = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html").read_text(encoding="utf-8")
i = s.find('<sc-if value="{{ interestOpen }}"'); print("--- interest modal ---"); print(s[i:i+900])
i = s.find('{{ form.pw }}'); print("--- sign-in password field ---"); print(s[max(0,i-500):i+700])
i = s.find('aria-label="Close panel"'); print("--- 38px close ---"); print(s[max(0,i-320):i+320])
PY
```

**No declaration may be typed by hand.** Every style string in A41.8 is pasted from that output; `frontend/tests/design-amendments.test.ts`'s `toContain` cases are what prove it.

- [ ] **Step 5: Wire the dialog to `SettingsUi.stepUp` in `app.setup.js`**

Task 2 left `adminSettings: { type: Object, default: () => makeAdminSettingsAdapter() }`. Replace the default with one that routes through the design's dialog. The dialog lives in the component instance, so the seam is a mutable holder `app.setup.js` owns and `logic.js` fills:

```js
  // A41: the step-up seam. `logic.js` writes `window.__pmStepUp` from `componentDidMount` (A41.11)
  // and the adapter reads it, so the ADAPTER never imports the component and the COMPONENT never
  // imports the adapter — the same one-way seam `perms` uses.
  adminSettings: { type: Object, default: () => makeAdminSettingsAdapter(stepUpUi()) },
```

with `stepUpUi()` declared once, above the props, and reused by every adapter that has a REAUTH action (Tasks 6, 11, 14, 18 and 19 all take it rather than writing their own):

```js
/** A41: the step-up seam, the ONE implementation of `StepUp`. `logic.js` writes
 *  `window.__pmStepUp` from componentDidMount (A41.11) and clears it on unmount. */
function stepUpUi() {
  return {
    stepUp: (perm, label, run, note) => new Promise((resolve) => {
      const open = window.__pmStepUp;
      // No dialog mounted — the API would answer 401 REAUTH_REQUIRED anyway, and a silent attempt
      // reads as a broken button. Resolve without running: the caller's own `refuse` says nothing,
      // because nothing was refused; nothing was attempted.
      if (!open) return resolve();
      open(perm, label, (collected) => Promise.resolve(run(collected)).then(resolve, resolve), note);
    }),
    refuse: (message) => window.alert(message)
  };
}
```

**The `window.__pmStepUp` global is a deviation-shaped choice and must be reviewed as one.** The alternative — passing the dialog down as a prop — cannot work: `logic.js` receives adapters, not the other way round. `window.__pmStepUp` is set in `componentDidMount` and cleared in `componentWillUnmount` (A41.11, beside A13.5's three document listeners and A24.23's unsubscribe), so nothing outlives the component. If a reviewer rejects the global, the fallback is for `adminVals()` to build the action buttons itself instead of `toSettingsRows`; say so as NEEDS_CONTEXT rather than improvising a third shape.

- [ ] **Step 6: Regenerate, characterise, gate**

```bash
cd frontend && npm run gen:design && npm run gen:logic && npm run gen:app
npm run typecheck && npm run build && npm test
```
`frontend/src/logic.test.ts`, `describe('A41 — the re-authentication dialog')`: the dialog is closed by default; `openReauth` opens it and records the label; a blank password sets `reauthErr` and never calls `confirm`; a rejected `confirm` leaves it OPEN with the server's message and never runs the action; a resolved `confirm` runs the action and then closes; Escape closes it and, with it closed, Escape still steps the lightbox (the A14.4 placement proof); `go()` and `signOut` clear it.

- [ ] **Step 7: Prove the frozen thirteen and every other baseline did not move**

Run C5 and then C6 of the closing sequence, with `PRE="$SCRATCH/a41-baselines-before.json"`. **Expected: `0 moved`, no `APPENDED` lines.** A closed dialog paints nothing — this is the A19 proof, re-taken.

- [ ] **Step 8: Commit**

```bash
git add frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts frontend/src/logic.test.ts \
        "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
        frontend/src/logic.js frontend/src/App.vue frontend/src/generated/pseudo.css frontend/src/app.setup.js
git commit -m "feat(design): A41.5-A41.11 — the re-authentication dialog

Composed from the interest modal's scrim and box, the sign-in card's
password field and error slot, and the docked panel's close control. It
closes only when the action it gated actually completed.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 5: Revoke through the dialog, the two real-browser states, the ledger (A41)

Task A36 **deleted** `UsersUi.reauthThen` and its `PERM_OF` table and left `Revoke` undrawn, because the design had no step-up element and unreachable code cannot be covered. It has one now.

**Re-basing states: ZERO re-based, ZERO appended to `screens.ts`, TWO appended to `smoke.spec.ts`** (`admin-settings`, `admin-reauth`) — **decision D12**: the reference receives no adapter, so a surface that exists only with one cannot be an approved state. **The thirteen frozen hashes must not move**, and `admin-users` in particular must not: Revoke is rendered from `src/admin/users.ts`'s `ACTIONS`, which the oracle's `DesignUserRow` arm bypasses — the design's own fourth fixture row has always shown Revoke, so the capture is unchanged either way. **Measure it.**

**Files:**
- Modify: `frontend/src/admin/users.ts` (`UsersUi` gains `stepUp`; `ACTIONS.active` gains `Revoke`), `frontend/src/admin/users.test.ts`
- Modify: `frontend/tests/screens.ts`, `frontend/tests/harness.ts`, `frontend/tests/harness.test.ts`
- Create: `frontend/tests/design-admin-settings.mjs`
- Modify: `frontend/tests/smoke.spec.ts`
- Modify: `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: Task 4's `openReauth(perm, label, run)` through `window.__pmStepUp`; Task 2's `SettingsUi`.
- Produces: nothing later tasks depend on except the ledger rows and the `harness.ts` stub shape, which **Tasks 7, 13, 16, 19, 21 and 23 each extend with one more URL**.

- [ ] **Step 1: Write the failing tests**

`frontend/src/admin/users.test.ts` — restore the case A36's report says it inverted:

```ts
it('puts Revoke — and only Revoke — behind a step-up, because it is the one decision in REAUTH', async () => {
  expect(await press('active', 'Revoke')).toEqual(['needsNote:revoke', 'stepUp:users.revoke', 'decide:a1:revoke:a reviewer note']);
  expect(await press('active', 'Suspend'), 'ruling 10.3: suspension is reversible and the API asks for no password')
    .not.toContain('stepUp:users.revoke');
});
```

`frontend/tests/smoke.spec.ts` — a real-browser case per surface:

```ts
test('the Settings tab reads the API, and an activation asks for a password first', async ({ page }) => {
  await reach(page, { screen: 'admin', persona: 'design' });
  await click(page, 'Settings');
  await expect(page.getByText('Market data visible to anonymous visitors')).toBeVisible();
  await expect(page.getByRole('button', { name: /^Activate / }).first()).toBeVisible();
  await page.getByRole('button', { name: /^Activate / }).first().click();
  await expect(page.getByText('Confirm your password to continue')).toBeVisible();
  const posted: string[] = [];
  page.on('request', (r) => { if (r.method() === 'POST') posted.push(new URL(r.url()).pathname); });
  await page.getByRole('button', { name: 'Cancel' }).click();
  expect(posted, 'a cancelled step-up issues nothing').toEqual([]);
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/admin/users.test.ts` → FAIL (`stepUp` is not in the recorded calls). Then `npm run test:e2e -- -g 'asks for a password first'` → FAIL (`Settings` tab not found before Task 3 is merged into this branch; it is, so the failure is the missing `Activate` button until `harness.ts` answers `/api/admin/settings`).

- [ ] **Step 3: Restore Revoke behind the step-up**

In `frontend/src/admin/users.ts`: make `UsersUi` extend `StepUp` (imported from `./settings` — **the one step-up shape, not a second declaration**); give `ACTIONS.active` its `Revoke` entry back with `tone: 'danger'`; and route it — and ONLY it — through `ui.stepUp('users.revoke', 'Revoke this account', () => decide(item, 'revoke', note), null)`, where `note` is the reviewer note `needsNote('revoke')` already collected. The dialog's own note argument is not used: `note: null` means no field is drawn, and `POST /api/admin/users/{id}/decide` takes the reviewer's note and not a second one. Derive "which action needs a step-up" from the generated `REAUTH` list, exactly as the deleted code did (`import { REAUTH } from '../auth/permissions'`), never from a literal: `const NEEDS_STEP_UP: Record<string, Permission> = { revoke: 'users.revoke' }` and `expect(REAUTH).toContain(NEEDS_STEP_UP.revoke)` as its own test case.

- [ ] **Step 4: Give the two states their oracle**

`frontend/tests/design-admin-settings.mjs` — the design's answer to `GET /api/admin/settings`, derived the way `design-admin-listings.mjs` is derived from `adminVals()`: a fixed `SettingsPayload` whose vintages and sign-up counts are stable, so the REFERENCE and the APP render identical rows. It is a payload, not rows: `toSettingsRows` runs on both targets.

`frontend/tests/harness.ts` — add `/api/admin/settings` to `collectionStubUrls()` and its body to `collectionStubBody()`, and pin the new stub in `harness.test.ts` the way A36's `/api/admin/users` stub is pinned.

**Decision D12 in full, because this is where it first bites.** `frontend/tests/screens.ts` entries run identical clicks on BOTH targets; the reference is the raw bundle driven by `data-props` and receives no adapter, so it would render a four-tab shell where the app renders five, and the pixel gate would fail. Therefore:
- `admin-settings` and `admin-reauth` go to `frontend/tests/smoke.spec.ts` (real Chromium, app only) and **NOT** to `screens.ts`;
- the ruled copy that most wants an oracle — the dialog's one new sentence — is pinned in `frontend/tests/dom.spec.ts`'s existing DOM oracle through `admin-users`, which both targets reach, by asserting the sentence is ABSENT on both while the dialog is closed. That proves the element adds nothing to a closed screen, which is precisely the frozen-hash claim.

This is the same gap A27.7 carries, for the same reason. **State it in the hand-back**; it is not a silent gap.

- [ ] **Step 5: Run the closing sequence, C1 and C2**

Eleven ledger rows — A41.1-A41.4 (Task 3) and A41.5-A41.11 (Task 4) — with `Consumes A40.3` on A41.4's row and `Consumes A41.3` on A41.5's.

- [ ] **Step 6: Run the closing sequence, C3 to C6**

The A41 paragraph goes after the A40 one. **C6's expected MOVED list for A41 is EMPTY, and its APPENDED list is empty too** — A41 adds nothing to `screens.ts` (decision D12).

- [ ] **Step 8: Commit and hand back**

```bash
git add frontend/src/admin/users.ts frontend/src/admin/users.test.ts frontend/tests/harness.ts \
        frontend/tests/harness.test.ts frontend/tests/design-admin-settings.mjs frontend/tests/smoke.spec.ts \
        frontend/tests/dom.spec.ts docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md CLAUDE.md
git commit -m "feat(admin): Revoke returns, behind the step-up it always needed (A41)

A36 deleted the unreachable step-up path because the design had no element
for it. A41 composes one, so users.revoke — the one decision in REAUTH — is
drawn and completes. Suspend is untouched (ruling 10.3).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

Hand back: the base SHA, the final SHA, the baseline-hash diff output, the four A41 entry ids and their ledger rows, the oracle limitation recorded in Step 4, and the `app.setup.js` `window.__pmStepUp` seam flagged for the reviewer.

---

## Task 6: `decideLicense`, and the dialog's optional note (A42)

The registry's only real write is `POST /api/admin/data-sources/{key}/license` (`licence.decide`, admin, REAUTH, AUDITED). A38 removed V3's unbacked "Assign review" / "Open question" buttons; this puts the real decision in their place. **The Foundation decides; the product gives them the button** (ruling 10.5).

**Re-basing states: NONE in this task** (no design file changes). **The thirteen frozen hashes must not move.**

**Files:**
- Modify: `frontend/src/admin/data_sources.ts` (A38's module), `frontend/src/admin/data_sources.test.ts`
- Modify: `frontend/tests/design-amendments.ts` + `.test.ts` (**one** entry, A42.1 — the dialog's note field), `frontend/src/logic.test.ts`
- Regenerated: the `.dc.html`, `logic.js`, `App.vue`, `pseudo.css`

**Interfaces:**
- Consumes: A38's `toDataSourceRows(rows, ui)`, `DataSourceRow`, `DataSourcesUi`, `makeAdminDataSourcesAdapter()`; A41's `openReauth(perm, label, run)` — **whose signature gains a fourth argument here**: `openReauth(perm, label, run, note)` where `note` is `null` (no field) or `{ label, placeholder }`.
- Produces:
  ```ts
  // frontend/src/admin/data_sources.ts
  /** A38's own interface, now EXTENDING `StepUp` from `./settings` — the one step-up shape, not a
   *  second declaration. A38's existing members are unchanged. */
  export interface DataSourcesUi extends StepUp { /* …A38's existing members… */ }
  export const LICENCE_NOTE_LABEL: string;          // 'Why (recorded in the licence ledger)'
  export const LICENCE_NOTE_PLACEHOLDER: string;    // 'Who reviewed the terms, and what they concluded.'
  ```
  **Task 7 reads `LICENCE_NOTE_LABEL` and `LICENCE_NOTE_PLACEHOLDER` for its cross-seam pin. Tasks 16 and 19 call the same four-argument `openReauth` with `note: null`.**

- [ ] **Step 1: Write the failing tests**

`frontend/src/admin/data_sources.test.ts`:

```ts
it('offers Clear and Block on an unresolved row, and only those two', () => {
  const row = toDataSourceRows([UNRESOLVED], ui())[0];
  expect(row[3].actions.map((a) => a.label)).toEqual(['Clear', 'Block']);
});

it('offers Clear on a blocked row — a block is reversible — and no second Block', () => {
  expect(toDataSourceRows([BLOCKED], ui())[0][3].actions.map((a) => a.label)).toEqual(['Clear']);
});

it('offers Block on a cleared row, and no second Clear', () => {
  expect(toDataSourceRows([CLEARED], ui())[0][3].actions.map((a) => a.label)).toEqual(['Block']);
});

it('keeps View terms where there is a licence URL, beside the decision', () => {
  expect(toDataSourceRows([UNRESOLVED_WITH_URL], ui())[0][3].actions.map((a) => a.label))
    .toEqual(['Clear', 'Block', 'View terms']);
});

it('asks for the password AND a mandatory note before it decides', async () => {
  const u = ui();
  await toDataSourceRows([UNRESOLVED], u)[0][3].actions[0].go();
  expect(u.calls[0]).toBe('stepUp:licence.decide:Clear esri_tiles:note');
});

it('POSTs the status and the note the dialog collected', async () => {
  const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);
  const u = ui({ noteAnswer: 'terms read 2026-09-14, no redistribution limit' });
  await toDataSourceRows([UNRESOLVED], u, decideVia(fetchMock))[0][3].actions[0].go();
  expect(fetchMock.mock.calls[0][0]).toBe('/api/admin/data-sources/esri_tiles/license');
  expect(JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string))
    .toEqual({ status: 'cleared', notes: 'terms read 2026-09-14, no redistribution limit' });
});

it('shows the server’s own refusal and changes nothing', async () => {
  vi.stubGlobal('fetch', vi.fn(async () =>
    new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'No such dataset.' } }), { status: 404 })));
  const u = ui({ noteAnswer: 'x' });
  await toDataSourceRows([UNRESOLVED], u)[0][3].actions[0].go();
  expect(u.calls).toContain('refuse:No such dataset.');
});
```

`frontend/tests/design-amendments.test.ts`:

```ts
describe('A42 — the licence decision', () => {
  const amended = readFileSync(AMENDED, 'utf8');
  it('gives the dialog the sign-in card’s own text field, mounted only when a note is asked for', () => {
    expect(amended).toContain('<sc-if value="{{ reauth.hasNote }}"');
    expect(amended).toContain('{{ reauth.noteLabel }}');
  });
  it('refuses a blank note rather than sending one', () => {
    expect(amended).toContain('if (s.reauthOpen && s.reauthOpen.note && !s.reauthNote.trim()) return this.setState({ reauthErr: "Record why before you continue." });');
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/admin/data_sources.test.ts tests/design-amendments.test.ts -t 'licence decision'`
Expected: FAIL — `expected [ 'View terms' ] to deeply equal [ 'Clear', 'Block' ]`, and the two design cases on `toContain`.

- [ ] **Step 3: Write A42.1 — the dialog's note slot**

ONE entry, CHAINED on A41.6, A41.7 and A41.8 (its `find` is each of those three's own output; the entry is therefore SPLIT into `A42.1a` (the members), `A42.1b` (the render value) and `A42.1c` (the markup) so each `find` is one earlier entry's output and each row can declare its own `Consumes`). Print and count all three first, with Task 4 Step 1's command pointed at the amended file.

- `A42.1a` — `submitReauth` gains ONE guard: a blank note where one was asked for is refused before the password is sent. `openReauth`'s signature, `reauthNote` and `run(note)` are already A41.6's (Task 4 wrote all four arguments), so this entry is the guard and nothing else. **`Consumes A41.6`.**
- `A42.1b` — the render value gains `hasNote`, `noteLabel`, `notePlaceholder`, `note`, `setNote`. **`Consumes A41.7`.**
- `A42.1c` — the markup gains the sign-in card's own `<label>`/`<textarea>` pair behind `<sc-if value="{{ reauth.hasNote }}">`, copied from the interest modal's own message field (`padding: 12px 13px; font-size: 14px; line-height: 1.6; color: var(--color-navy); border: 1px solid var(--border-subtle); border-radius: 6px; outline: none; resize: vertical;`). **`Consumes A41.8`.**

Extract that textarea's declarations before writing:
```bash
python3 -c "import pathlib;s=pathlib.Path('docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html').read_text(encoding='utf-8');i=s.find('Message to the seller');print(s[i-400:i+600])"
```

- [ ] **Step 4: Write `decideLicense` in `admin/data_sources.ts`**

```ts
/** The one human write the registry has. `licence.decide` is admin-only, in REAUTH and in AUDITED,
 *  so the button opens the dialog and the DECISION is issued with the note the dialog collected.
 *  The note is mandatory HERE and optional in the API (decision D10): `LicenseDecision.notes` is a
 *  published contract other callers hold, and a screen's own requirement is not the route's. */
export const LICENCE_NOTE_LABEL = 'Why (recorded in the licence ledger)';
export const LICENCE_NOTE_PLACEHOLDER = 'Who reviewed the terms, and what they concluded.';

const DECISIONS: Record<string, { label: string; status: 'cleared' | 'blocked'; tone: string | undefined }> = {
  cleared: { label: 'Clear', status: 'cleared', tone: 'primary' },
  blocked: { label: 'Block', status: 'blocked', tone: 'danger' }
};

/** Which decisions a row may take. A cleared row may be blocked; a blocked or unresolved row may be
 *  cleared; an unresolved row may be blocked. Never the status it already holds — an action that
 *  changes nothing is not an action. */
function decisionsFor(status: string): Array<{ label: string; status: 'cleared' | 'blocked'; tone: string | undefined }> {
  return (['cleared', 'blocked'] as const).filter((s) => s !== status).map((s) => DECISIONS[s]);
}
```
and, inside `toDataSourceRows`'s action cell, one `A(d.label, d.tone, () => ui.stepUp('licence.decide', `${d.label} ${row.dataset_key}`, (note) => decide(row.dataset_key, d.status, note), { label: LICENCE_NOTE_LABEL, placeholder: LICENCE_NOTE_PLACEHOLDER }))` per entry of `decisionsFor(row.license_status)`, with `View terms` appended last exactly as A38 wrote it.

`decide` posts `{ status, notes }` to `/data-sources/${encodeURIComponent(key)}/license` through A38's own `send()` and calls `ui.refuse(await refusalMessage(res, 'That licence decision could not be recorded.'))` on a refusal. **No reload is issued**: the row's pill is re-read by the tab's own `loadAdmin()` on the next arrival, which is `admin/listings.ts`'s recorded behaviour and is not widened here.

- [ ] **Step 5: Regenerate, run both gates**

```bash
cd frontend && npm run gen:design && npm run gen:logic && npm run gen:app
npm run typecheck && npm run build && npm test
```
Expected: PASS at 100 %.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/admin/data_sources.ts frontend/src/admin/data_sources.test.ts \
        frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts frontend/src/logic.test.ts \
        "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
        frontend/src/logic.js frontend/src/App.vue frontend/src/generated/pseudo.css
git commit -m "feat(admin): the licence decision, with the note the ledger asks for (A42.1)

Clear and Block on every Data Sources row, each through the A41 dialog with
a mandatory note. The Esri rows A38 registered unresolved are decided here,
by the VIN Foundation — the product takes no view (ruling 10.5).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 7: Clear / Block on the Data Sources tab — the oracle and the ledger (A42)

The adapter offers the buttons; the DESIGN must let the tab's rows carry them, which A38.1's ternary already does — so this task is small on purpose, and its real content is the oracle and the ledger.

**Re-basing states: ZERO re-based, ONE appended** — `admin-data-sources-decide`, the dialog open over the tab, captured on the app in `smoke.spec.ts` (Task 5 Step 4's limitation applies again: the reference cannot be handed an adapter). **`admin-data-sources` must not move**: its oracle fixture is the design's own five rows through A38's `DesignDataSourceRow` arm, which carries its own actions verbatim and never reaches `decisionsFor`. **Measure it.**

**Files:** `frontend/tests/harness.ts`, `frontend/tests/smoke.spec.ts`, `docs/design-reference/…/LOCAL_AMENDMENTS.md`, `CLAUDE.md`.

**Interfaces:** consumes Task 6's `LICENCE_NOTE_LABEL`, `LICENCE_NOTE_PLACEHOLDER`; produces nothing.

- [ ] **Step 1: Write the failing real-browser case**

```ts
test('a licence decision asks for the password and the why, and records both', async ({ page }) => {
  await reach(page, { screen: 'admin', persona: 'design' });
  await click(page, 'Data Sources');
  await page.getByRole('button', { name: 'Clear' }).first().click();
  await expect(page.getByText('Confirm your password to continue')).toBeVisible();
  await expect(page.getByText('Why (recorded in the licence ledger)')).toBeVisible();
  const posted: Array<{ path: string; body: string }> = [];
  page.on('request', (r) => { if (r.method() === 'POST') posted.push({ path: new URL(r.url()).pathname, body: r.postData() ?? '' }); });
  await page.getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByText('Record why before you continue.')).toBeVisible();
  expect(posted, 'a blank note issues nothing, not even the re-auth').toEqual([]);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npm run test:e2e -- -g 'records both'`
Expected: FAIL — the harness does not yet answer `POST /api/admin/data-sources/*/license`, so `Clear` is present but the case's third assertion never arrives.

- [ ] **Step 3: Teach the harness the decision route**

`frontend/tests/harness.ts`: route `POST **/api/admin/data-sources/*/license` to a 200 with the row's own body, and pin it in `harness.test.ts`. This is a stub for the SMOKE project only; the visual and DOM projects never post.

- [ ] **Step 4: Confirm the family is complete at three entries, and that the footnote needs none**

**A42 is `A42.1` (the dialog's note in the class members), `A42.2` (its render value) and `A42.3` (its markup)** — Task 6 wrote all three; nothing further is added to the design here. Two checks, both recorded in the hand-back:

1. **The Data Sources footnote is left ALONE.** Read it: *"No dataset reaches production until its license is recorded here. Anything marked unresolved is excluded from listings and from the map until the VIN Foundation clears it."* A38 made the first sentence true by registering the Esri rows; A42 makes the second actionable. A sentence that became true needs no edit, and editing it would be prose churn under the A27.5 rule (which fires when a release makes a sentence FALSE, not when it makes one true).
2. **`LICENCE_NOTE_LABEL` / `LICENCE_NOTE_PLACEHOLDER` are pinned across the seam in `frontend/src/logic.test.ts`, not in the design** — the design renders `{{ reauth.noteLabel }}`, which the adapter supplies, so there is no second copy of either string to keep in step.

- [ ] **Step 5: Run the closing sequence, C1 to C6**

Three ledger rows — A42.1, A42.2, A42.3 — carrying `Consumes A41.6`, `Consumes A41.7` and `Consumes A41.8` respectively. **C6's expected MOVED list is EMPTY, and its APPENDED list is empty**: the one new state is a `smoke.spec.ts` case, which takes no baseline.

- [ ] **Step 6: Commit and hand back**

```bash
git add frontend/tests/harness.ts frontend/tests/harness.test.ts frontend/tests/smoke.spec.ts \
        frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts \
        docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md CLAUDE.md
git commit -m "feat(admin): the Data Sources tab decides a licence (A42)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

Hand back: the base and final SHAs, the baseline-hash diff, the three A42 entry ids, and the footnote check from Step 4.

---

## Task 8: `migrations/096_request.sql` and the buyer routes (A43)

**There is no request table and no request route anywhere in the product.** The buyer's "I'm interested", My Requests, the seller inbox and the admin tab are four in-memory fixtures in `logic.js`. This is the build, and it starts with the model and the two routes the BUYER needs.

**Re-basing states: NONE** (no design file changes). **The thirteen frozen hashes must not move.**

**Files:**
- Create: `migrations/096_request.sql`, `app/api/requests.py`, `tests/api/test_requests.py`
- Modify: `app/main.py` (mount `requests_router` inside the `site_mode == "app"` block, beside `listings_router`)
- Modify: `docs/integrations/market-data-api.md`

**Interfaces:**
- Consumes: `app.auth.deps.require`, `app.auth.audit.write`, `app.db.sync_conn`, `app.api.listings`'s own `_error` shape.
- Produces:
  ```python
  # app/api/requests.py
  router: APIRouter                   # prefix "/api"
  STATUSES = ("pending", "accepted", "declined")
  MAX_MESSAGE = 4_000
  AWAITING_HOURS = 48                 # spec §5's badge: pending and older than this

  # POST /api/requests                {listing_id, message}  -> 201 {id, status, created_at}
  # GET  /api/requests/mine           -> {items: [RequestOut], counts: {pending, accepted, declined}}
  ```
  `RequestOut`, which **Task 11's `frontend/src/requests/buyer.ts` types verbatim**:
  ```jsonc
  { "id": "uuid", "listing_id": "uuid", "listing_title": "Small animal practice — Cedar Park",
    "listing_market": "Austin, TX", "seller_name": "Dr. James Whitfield|null",
    "message": "…", "status": "pending", "created_at": "…Z", "decided_at": "…Z|null",
    "reply": "…|null", "documents_released": false }
  ```
  **Task 9 adds `GET /api/seller/requests` and `POST /api/seller/requests/{id}/decide` to this same module; Task 10 adds the two admin routes. Neither re-shapes `RequestOut`.**

- [ ] **Step 1: Write `migrations/096_request.sql`**

```sql
-- The buyer's request to a seller, and its history (admin control surface spec §5).
--
-- There was no request table at all before this: the interest modal, My Requests, the seller inbox
-- and the admin Requests tab were four in-memory fixtures in the design's own script. The three
-- statuses are V3's own three; the design's fourth pill, "Review", backs no detector and is not
-- built (the `admin/listings.ts` "Flagged" rule).
--
-- `documents_released` is the column `app/api/seller_listings.read_document`'s own comment has
-- named since Task SL7 as the arm to be added "when a `request` table exists". It is set by the
-- seller's accept and by nothing else, so a document's readability is a decision somebody took
-- rather than a side effect of two flags lining up.
CREATE TABLE request (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  listing_id          uuid        NOT NULL REFERENCES listing (id) ON DELETE CASCADE,
  buyer_account_id    uuid        NOT NULL REFERENCES account (id) ON DELETE CASCADE,
  message             text        NOT NULL CHECK (length(message) BETWEEN 1 AND 4000),
  status              text        NOT NULL DEFAULT 'pending'
                                  CHECK (status IN ('pending','accepted','declined')),
  reply               text        CHECK (reply IS NULL OR length(reply) <= 4000),
  documents_released  boolean     NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now(),
  decided_at          timestamptz,
  decided_by          uuid        REFERENCES account (id),
  -- A decided row carries its decision's time and author; a pending one carries neither. Stated as
  -- a constraint rather than trusted to the handler, because three surfaces read these columns.
  CONSTRAINT request_decided_together CHECK (
    (status = 'pending' AND decided_at IS NULL AND decided_by IS NULL)
    OR (status <> 'pending' AND decided_at IS NOT NULL))
);

-- One open request per (buyer, listing): a buyer who asks twice is asking again, not twice. A
-- DECIDED row does not block a later one — a declined buyer whose circumstances changed may ask
-- again, which is what the design's own "The listing may already be under contract" leaves open.
CREATE UNIQUE INDEX request_one_open_per_buyer_listing_idx
    ON request (listing_id, buyer_account_id) WHERE status = 'pending';
CREATE INDEX request_by_buyer_idx   ON request (buyer_account_id, created_at DESC, id DESC);
CREATE INDEX request_by_listing_idx ON request (listing_id, created_at DESC, id DESC);
CREATE INDEX request_open_age_idx   ON request (created_at) WHERE status = 'pending';

-- The history the admin tab's Age column reads, and the only place a reminder would ever be
-- recorded if one is ever built. Append-only by convention, not by trigger: `audit_log` is the
-- tamper-evident ledger and this is the request's own timeline.
CREATE TABLE request_event (
  id          bigserial PRIMARY KEY,
  request_id  uuid        NOT NULL REFERENCES request (id) ON DELETE CASCADE,
  at          timestamptz NOT NULL DEFAULT now(),
  actor_role  text        NOT NULL,
  kind        text        NOT NULL
              CHECK (kind IN ('created','accepted','declined','packet_released','message_viewed'))
);
CREATE INDEX request_event_by_request_idx ON request_event (request_id, at DESC, id DESC);
```

- [ ] **Step 2: Write the failing tests**

`tests/api/test_requests.py` — the buyer half:

```python
def test_a_buyer_creates_a_request_and_it_starts_pending(buyer_client, published_listing):
    r = buyer_client.post("/api/requests", json={"listing_id": published_listing.id, "message": "Phased transition?"})
    assert r.status_code == 201 and r.json()["status"] == "pending"


def test_the_creation_writes_one_created_event_and_no_audit_row(buyer_client, published_listing, events_of, audit_rows):
    body = buyer_client.post("/api/requests", json={"listing_id": published_listing.id, "message": "x"}).json()
    assert [e["kind"] for e in events_of(body["id"])] == ["created"]
    assert [a for a in audit_rows() if a["target_type"] == "request"] == []


def test_a_second_open_request_for_the_same_listing_is_refused(buyer_client, published_listing):
    buyer_client.post("/api/requests", json={"listing_id": published_listing.id, "message": "x"})
    r = buyer_client.post("/api/requests", json={"listing_id": published_listing.id, "message": "y"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_ASKED"


def test_a_buyer_may_ask_again_once_the_first_request_was_decided(buyer_client, declined_request):
    r = buyer_client.post("/api/requests", json={"listing_id": declined_request.listing_id, "message": "again"})
    assert r.status_code == 201


def test_a_request_for_an_unpublished_listing_is_refused(buyer_client, draft_listing):
    r = buyer_client.post("/api/requests", json={"listing_id": draft_listing.id, "message": "x"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND"


def test_a_blank_or_oversized_message_is_refused(buyer_client, published_listing):
    assert buyer_client.post("/api/requests", json={"listing_id": published_listing.id, "message": "  "}).status_code == 422
    assert buyer_client.post("/api/requests", json={"listing_id": published_listing.id, "message": "x" * 4001}).status_code == 422


def test_an_applicant_cannot_create_a_request(applicant_client, published_listing):
    assert applicant_client.post("/api/requests", json={"listing_id": published_listing.id, "message": "x"}).status_code == 403


def test_mine_returns_only_this_buyer_s_requests_newest_first(buyer_client, two_buyers_with_requests):
    items = buyer_client.get("/api/requests/mine").json()["items"]
    assert [i["id"] for i in items] == two_buyers_with_requests.first_buyers_ids
    assert all(i["listing_title"] for i in items), "every row names the practice the design's card shows"


def test_mine_carries_the_three_counts_the_design_s_pills_read(buyer_client, mixed_requests):
    assert buyer_client.get("/api/requests/mine").json()["counts"] == {"pending": 1, "accepted": 1, "declined": 1}


def test_mine_never_exposes_another_buyer_s_message(buyer_client, two_buyers_with_requests):
    assert all("other buyer" not in i["message"] for i in buyer_client.get("/api/requests/mine").json()["items"])
```

- [ ] **Step 3: Run them to verify they fail**

Run: `poetry run pytest tests/api/test_requests.py -q`
Expected: every case FAILS with `assert 404 == 201` / `== 200` — no router.

- [ ] **Step 4: Write `app/api/requests.py`'s buyer half**

```python
"""Requests — the buyer asks, the seller answers, staff can see that it happened (admin control
surface spec §5).

Before this module there was no `request` table and no request route anywhere in the product: the
interest modal, My Requests, the seller inbox and the admin Requests tab were four in-memory
fixtures in the design's own script. `migrations/096_request.sql` is the model.

Three statuses, V3's own three. The design's fourth pill — "Review", over a row reading "Volume
pattern flagged automatically" — backs no detector and is NOT built; it stays an oracle-only
fixture, exactly as the "Flagged" listing does (`app/api/admin_listings.py`'s rule).

Shapes that are load-bearing here, each already broken somewhere in this codebase before:

* **Every guard is a module-level constant, never wrapped** — `tests/auth/test_permissions.py`
  resolves a route's permission by the guard's object IDENTITY.
* **`audit.write(` is called in the audited endpoint's OWN body.** Only ONE route here is audited:
  `GET /api/admin/requests/{id}/message`, whose permission `abuse.investigate` is in `AUDITED`.
  Creating and answering a request are not audited — they are the product working, not an
  administrative act, and one row per buyer message would fill an append-only table with ordinary
  traffic. The request's OWN timeline is `request_event`.
* **No bare `HTTPException`**: a refusal carries decision A5's `{"error": {"code", "message"}}`.
"""
from __future__ import annotations

from contextlib import closing
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import audit
from app.auth import sessions as S
from app.auth.deps import require
from app.db import sync_conn

router = APIRouter(prefix="/api")

REQUIRE_CREATE = require("request.create")
REQUIRE_READ_OWN = require("request.read_own")
Asker = Annotated[S.Principal, Depends(REQUIRE_CREATE)]
OwnReader = Annotated[S.Principal, Depends(REQUIRE_READ_OWN)]

STATUSES = ("pending", "accepted", "declined")
MAX_MESSAGE = 4_000
#: Spec §5's badge: a request still `pending` after this is what the design calls "Awaiting seller".
AWAITING_HOURS = 48

# `listing_title` is composed the way the design's own card composes it (`logic.js`'s `reqList`):
# "<Type> practice — <area>". It is composed in SQL rather than by the client because three
# surfaces print it and one composition is how they stay the same sentence.
MINE_SQL = """
SELECT r.id, r.listing_id, initcap(l.type) || ' practice — ' || l.city, l.market,
       s.display_name, r.message, r.status, r.created_at, r.decided_at, r.reply, r.documents_released
  FROM request r
  JOIN listing l ON l.id = r.listing_id
  LEFT JOIN account s ON s.id = l.seller_id
 WHERE r.buyer_account_id = %s
 ORDER BY r.created_at DESC, r.id DESC
 LIMIT %s
"""
COUNTS_SQL = "SELECT status, count(*) FROM request WHERE buyer_account_id = %s GROUP BY 1"
MAX_LIST = 200


def _error(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _out(r: tuple[Any, ...]) -> dict[str, Any]:
    return {"id": str(r[0]), "listing_id": str(r[1]), "listing_title": r[2], "listing_market": r[3],
            "seller_name": r[4], "message": r[5], "status": r[6], "created_at": r[7].isoformat(),
            "decided_at": _iso(r[8]), "reply": r[9], "documents_released": r[10]}


class RequestIn(BaseModel):
    listing_id: UUID
    message: str = Field(min_length=1, max_length=MAX_MESSAGE)


@router.post("/requests", status_code=201)
def create_request(body: RequestIn, principal: Asker) -> JSONResponse:
    """The interest modal's real submit.

    A plain `def` for the reason every module here gives (`admin_data_sources.list_data_sources`):
    blocking psycopg2 belongs in the threadpool.

    Refused for an unpublished listing with the SAME 404 an unknown id gets: whether a draft exists
    is the seller's business, and two distinguishable outcomes would say so.

    One open request per (buyer, listing) is enforced by the partial unique index, not by a read —
    two simultaneous clicks would both pass a SELECT. The `IntegrityError` is caught by name here
    rather than pre-checked."""
    if not body.message.strip():
        return _error("MESSAGE_REQUIRED", "Add a short message so the seller knows what you are asking for.", 422)
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM listing WHERE id=%s AND status='published'", (body.listing_id,))
        if cur.fetchone() is None:
            return _error("NOT_FOUND", "No such listing.", 404)
        cur.execute("SAVEPOINT ask")
        try:
            cur.execute("INSERT INTO request (listing_id, buyer_account_id, message)"
                        " VALUES (%s,%s,%s) RETURNING id, created_at",
                        (body.listing_id, principal.account_id, body.message.strip()))
        except Exception:  # noqa: BLE001 — the partial unique index is the only constraint reachable here
            cur.execute("ROLLBACK TO SAVEPOINT ask")
            return _error("ALREADY_ASKED", "You already have an open request for this listing.", 409)
        request_id, created_at = cast("tuple[UUID, datetime]", cur.fetchone())
        cur.execute("INSERT INTO request_event (request_id, actor_role, kind) VALUES (%s,%s,'created')",
                    (request_id, ",".join(sorted(principal.roles))))
    return JSONResponse({"id": str(request_id), "status": "pending", "created_at": created_at.isoformat()},
                        status_code=201)


@router.get("/requests/mine")
def my_requests(principal: OwnReader) -> dict[str, Any]:
    """My Requests. Every row is this account's own — the filter is the WHERE clause, never a
    client-side one — so another buyer's message is not merely hidden, it is never selected."""
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute(MINE_SQL, (principal.account_id, MAX_LIST))
        items = [_out(row) for row in cur.fetchall()]
        cur.execute(COUNTS_SQL, (principal.account_id,))
        grouped = dict(cast("list[tuple[str, int]]", cur.fetchall()))
    return {"items": items, "counts": {s: grouped.get(s, 0) for s in STATUSES}}
```

**`initcap(l.type)` and `l.city`/`l.market` are placeholders for the real column names — check them** (`sed -n '1,80p' migrations/016_listing.sql` and `grep -n "def serialise" -A 30 app/api/listings.py`) and use whatever `app/api/listings.py::serialise` uses to compose the buyer-facing title today, so the request card and the listing card say the same thing. If `serialise` composes it in Python rather than in SQL, compose it the same way here and delete the SQL expression — **one composition, in the place the product already has one.**

- [ ] **Step 5: Mount the router, run the tests**

`app/main.py`, inside `site_mode == "app"`, immediately after `app.include_router(listings_router)`, with the block's own comment shape. Then:

```bash
poetry run python scripts/migrate.py
poetry run pytest tests/api/test_requests.py -q
```
Expected: PASS.

- [ ] **Step 6: The whole backend gate, then commit**

```bash
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m "not timing"
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m timing -p no:randomly --cov-append --cov-report=xml --cov-fail-under=100
git add migrations/096_request.sql app/api/requests.py app/main.py tests/api/test_requests.py tests/api/conftest.py docs/integrations/market-data-api.md
git commit -m "feat(requests): the request model, and the buyer's two routes

There was no request table and no request route anywhere in the product.
POST /api/requests is the interest modal's real submit; GET /api/requests/mine
is My Requests. One open request per buyer per listing, enforced by a partial
unique index rather than by a read.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 9: The seller routes, and the document packet the accept releases (A43)

The seller's own inbox, and **the deferred arm `app/api/seller_listings.read_document` has documented since Task SL7**, verbatim in its own comment: *"the buyer-with-an-accepted-request arm belongs to the requests sub-project and is the arm that will be added here when a `request` table exists"*, with the expression it will take already written down — `… or (has_accepted_request and _disclosed and _status == "published")`. The design's seller-inbox copy already promises it: *"You released the financial packet and floor plan to this buyer."*

**Re-basing states: NONE.** **The thirteen frozen hashes must not move.**

**Files:**
- Modify: `app/api/requests.py` (the seller half), `app/api/seller_listings.py:1251-1297` (`read_document`'s allow test), `tests/api/test_requests.py`, `tests/api/test_seller_listings.py`
- Modify: `docs/integrations/market-data-api.md`

**Interfaces:**
- Consumes: Task 8's `router`, `_out`, `_error`, `STATUSES`, `MAX_MESSAGE`, the `request`/`request_event` tables.
- Produces:
  ```python
  # GET  /api/seller/requests                  -> {items: [RequestOut + {"buyer_name", "buyer_role_label"}], counts: {...}}
  # POST /api/seller/requests/{request_id}/decide  {action: "accept"|"decline", reply: str}
  #                                            -> 200 {id, status, documents_released, reply}
  DECISIONS = {"accept": ("accepted", True), "decline": ("declined", False)}
  ```
  **Task 11's `frontend/src/requests/seller.ts` types this verbatim.** `buyer_role_label` is `app.auth.labels.role_label(...)` — the same function `/api/me` uses, so the inbox's "Approved buyer · …" is the string the buyer's own header shows and not a second composition.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_seller_sees_requests_for_their_own_listings_and_no_others(seller_client, requests_across_two_sellers):
    items = seller_client.get("/api/seller/requests").json()["items"]
    assert {i["id"] for i in items} == set(requests_across_two_sellers.mine)


def test_the_inbox_names_the_buyer_with_the_label_their_own_header_shows(seller_client, one_pending_request):
    item = seller_client.get("/api/seller/requests").json()["items"][0]
    assert item["buyer_role_label"] == "Approved buyer"


def test_accepting_releases_the_document_packet_and_records_two_events(seller_client, one_pending_request, events_of):
    r = seller_client.post(f"/api/seller/requests/{one_pending_request.id}/decide",
                           json={"action": "accept", "reply": "Happy to share more."})
    assert r.status_code == 200 and r.json()["documents_released"] is True
    assert [e["kind"] for e in events_of(one_pending_request.id)] == ["created", "accepted", "packet_released"]


def test_declining_releases_nothing(seller_client, one_pending_request):
    r = seller_client.post(f"/api/seller/requests/{one_pending_request.id}/decide",
                           json={"action": "decline", "reply": "Not engaging further."})
    assert r.json()["status"] == "declined" and r.json()["documents_released"] is False


def test_a_decided_request_cannot_be_decided_again(seller_client, accepted_request):
    r = seller_client.post(f"/api/seller/requests/{accepted_request.id}/decide", json={"action": "decline", "reply": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_DECIDED"


def test_a_seller_cannot_decide_another_seller_s_request(seller_client, another_sellers_request):
    r = seller_client.post(f"/api/seller/requests/{another_sellers_request.id}/decide", json={"action": "accept", "reply": "x"})
    assert r.status_code == 404, "whose listing it is is not this seller's business"


def test_a_buyer_with_an_accepted_request_can_read_a_disclosed_document_on_a_published_listing(
        buyer_client, accepted_request_with_documents):
    r = buyer_client.get(f"/api/seller/listings/{accepted_request_with_documents.listing_id}"
                         f"/documents/{accepted_request_with_documents.document_id}")
    assert r.status_code == 200


def test_a_buyer_whose_request_is_only_pending_is_still_locked_out(buyer_client, pending_request_with_documents):
    r = buyer_client.get(f"/api/seller/listings/{pending_request_with_documents.listing_id}"
                         f"/documents/{pending_request_with_documents.document_id}")
    assert r.status_code == 403 and r.json()["error"]["code"] == "LOCKED"


def test_an_accepted_request_does_not_unlock_a_listing_whose_documents_are_not_disclosed(
        buyer_client, accepted_request_documents_undisclosed):
    r = buyer_client.get(f"/api/seller/listings/{accepted_request_documents_undisclosed.listing_id}"
                         f"/documents/{accepted_request_documents_undisclosed.document_id}")
    assert r.status_code == 403


def test_an_accepted_request_does_not_unlock_a_listing_that_is_no_longer_published(
        buyer_client, accepted_request_listing_paused):
    r = buyer_client.get(f"/api/seller/listings/{accepted_request_listing_paused.listing_id}"
                         f"/documents/{accepted_request_listing_paused.document_id}")
    assert r.status_code == 403
```

- [ ] **Step 2: Run them to verify they fail**

Run: `poetry run pytest tests/api/test_requests.py tests/api/test_seller_listings.py -q -k "seller_requests or document"`
Expected: 404s on the two new routes; the four document cases fail with `403 != 200` on the first and PASS on the other three — **the three that already pass are the regression guard the arm must not break**, and they are written now so the arm is proved to narrow the lock rather than open it.

- [ ] **Step 3: Write the seller half of `app/api/requests.py`**

```python
REQUIRE_ANSWER_OWN = require("request.answer_own")
Answerer = Annotated[S.Principal, Depends(REQUIRE_ANSWER_OWN)]

#: action -> (status it reaches, whether it releases the document packet). Accepting is the ONLY
#: thing that sets `documents_released`, which is what makes a document's readability a decision
#: somebody took rather than two flags lining up (`seller_listings.read_document`'s own warning).
DECISIONS = {"accept": ("accepted", True), "decline": ("declined", False)}

# Written out in full rather than derived from `MINE_SQL` by string surgery: the inbox selects the
# BUYER as well, which the buyer's own view has no need of, and a query that differs by one clause
# from another is still a different query.
INBOX_SQL = """
SELECT r.id, r.listing_id, initcap(l.type) || ' practice — ' || l.city, l.market,
       s.display_name, r.message, r.status, r.created_at, r.decided_at, r.reply, r.documents_released,
       b.display_name, b.affiliation_label,
       COALESCE((SELECT array_agg(g.role) FROM role_grant g WHERE g.account_id = b.id), '{}')
  FROM request r
  JOIN listing l ON l.id = r.listing_id
  LEFT JOIN account s ON s.id = l.seller_id
  LEFT JOIN account b ON b.id = r.buyer_account_id
 WHERE l.seller_id = %s
 ORDER BY r.created_at DESC, r.id DESC
 LIMIT %s
"""


class DecisionIn(BaseModel):
    action: str = Field(max_length=16)
    reply: str = Field(min_length=1, max_length=MAX_MESSAGE)
```

`buyer_role_label` is `labels.role_label(frozenset(roles), affiliation)` — **the same function `/api/me` uses**, so the inbox's "Approved buyer · …" is the string the buyer's own header shows and not a second composition. Check `role_grant`'s real column names before writing the lateral (`sed -n '1,60p' migrations/011_applications_roles.sql`) and use whatever `admin_users._grants` reads.

```python
@router.get("/seller/requests")
def seller_inbox(principal: Answerer) -> dict[str, Any]:
    """Every request against a listing this account owns. The ownership test is the WHERE clause."""


@router.post("/seller/requests/{request_id}/decide")
def decide_request(request_id: UUID, body: DecisionIn, principal: Answerer) -> JSONResponse:
    """Accept or decline, once.

    The row is locked (`FOR UPDATE`) and its status re-read inside the transaction, so two clicks
    cannot both decide it; the ownership test is part of the same locked read, so a request against
    somebody else's listing is a 404 — whose listing it is is not this caller's business.

    Accepting sets `documents_released` and writes TWO events, `accepted` then `packet_released`,
    because the seller's own copy names the release as a separate thing they did ("You released the
    financial packet and floor plan to this buyer") and the admin tab's Age sub-line reads the last
    event. Declining writes one."""
    if body.action not in DECISIONS:
        return _error("BAD_ACTION", f"action must be one of {', '.join(sorted(DECISIONS))}.", 422)
    status, releases = DECISIONS[body.action]
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT r.status FROM request r JOIN listing l ON l.id = r.listing_id"
                    " WHERE r.id = %s AND l.seller_id = %s FOR UPDATE OF r", (request_id, principal.account_id))
        found = cur.fetchone()
        if found is None:
            return _error("NOT_FOUND", "No such request.", 404)
        if cast("tuple[str]", found)[0] != "pending":
            return _error("ALREADY_DECIDED", "This request has already been answered.", 409)
        cur.execute("UPDATE request SET status=%s, reply=%s, documents_released=%s, decided_at=now(), decided_by=%s"
                    " WHERE id=%s", (status, body.reply.strip(), releases, principal.account_id, request_id))
        role = ",".join(sorted(principal.roles))
        cur.execute("INSERT INTO request_event (request_id, actor_role, kind) VALUES (%s,%s,%s)",
                    (request_id, role, status))
        if releases:
            cur.execute("INSERT INTO request_event (request_id, actor_role, kind) VALUES (%s,%s,'packet_released')",
                        (request_id, role))
    return JSONResponse({"id": str(request_id), "status": status, "documents_released": releases,
                         "reply": body.reply.strip()})
```

- [ ] **Step 4: Open the arm in `seller_listings.read_document`**

The query already selects `l.documents_disclosed` and `l.status` and binds them to `_disclosed`/`_status` explicitly so this change needs no query change. Replace the allow test — and REWRITE the comment, because the sentence it carries becomes false the moment the arm lands:

```python
        # Owner, staff, or a buyer the SELLER accepted (Major-1, A-SL18 (1); the arm this comment
        # has named since Task SL7 now exists — `migrations/096_request.sql`). All three terms are
        # required, and each one is a different person's decision:
        #   * `documents_released` — the seller ACCEPTED this buyer's request (`POST
        #     /api/seller/requests/{id}/decide`), which is the act the design's own copy describes
        #     as "You released the financial packet and floor plan to this buyer";
        #   * `_disclosed` — the seller has not since locked the listing's documents;
        #   * `_status == "published"` — the listing is still on the market.
        # A round of this module once let the last two stand in for the first, which let ANY signed
        # -in member download a document the moment a seller flipped one switch, with no request and
        # no accept. The request term is what that arm was always missing.
        #
        # Staff by the MATRIX, not by a hard-coded role tuple: `listing.review` is the staff/admin
        # capability the reviewer already holds, so a later role change moves both together.
        accepted = False
        if seller_id != principal.account_id and not P.allowed("listing.review", principal):
            with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
                cur.execute("SELECT 1 FROM request WHERE listing_id=%s AND buyer_account_id=%s"
                            " AND status='accepted' AND documents_released",
                            (parsed_listing, principal.account_id))
                accepted = cur.fetchone() is not None
        allowed = (seller_id == principal.account_id or P.allowed("listing.review", principal)
                   or (accepted and _disclosed and _status == "published"))
```

**The extra query runs only for a caller who is neither the owner nor staff** — the two who reach documents today pay nothing for the new arm. Rename `_disclosed`/`_status` to `disclosed`/`status_` in the same commit now that they are read; leave the tuple unpack in the same position.

- [ ] **Step 5: Run the tests, then the whole backend gate**

Expected: PASS, including the three regression cases from Step 2. Then the two-command coverage gate at 100 %.

- [ ] **Step 6: Commit**

```bash
git add app/api/requests.py app/api/seller_listings.py tests/api/test_requests.py \
        tests/api/test_seller_listings.py tests/api/conftest.py docs/integrations/market-data-api.md
git commit -m "feat(requests): the seller's inbox, and the packet an accept releases

read_document's buyer arm has been documented since Task SL7 as 'the arm
that will be added when a request table exists'. It exists. All three terms
are required: the seller accepted, the documents are still disclosed, and
the listing is still published.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 10: The admin routes, and `/api/me`'s two served facts (A43)

Staff may see **that** a request exists and whether it was answered; the message itself is an abuse investigation, and **every such view is logged** — which is what the design's own Requests footer has promised since V3: *"Message contents are visible only in an abuse investigation, and every such view is logged."*

And the interest modal's two literals — `{ k: "License state", v: "Texas" }` and `{ k: "VIN Foundation status", v: "Approved buyer" }` — become served, so a member in New Mexico is not told they are licensed in Texas.

**Re-basing states: NONE.** **The thirteen frozen hashes must not move.**

**Files:**
- Modify: `app/api/requests.py` (the admin half), `app/api/auth.py:287-302` (`me_payload`), `tests/api/test_requests.py`, `tests/api/test_auth.py`
- Modify: `frontend/src/auth/me.ts` (the `Me` type gains `license_state`), `frontend/src/auth/me.test.ts`
- Modify: `docs/integrations/market-data-api.md`

**Interfaces:**
- Consumes: Task 8/9's module; `app.auth.audit.write`; `app.api.applications.SELLER_REQUIRED`/`BUYER_REQUIRED` field names.
- Produces:
  ```python
  # GET /api/admin/requests   (request.oversee, staff)  -> {items: [AdminRequestOut], counts: {...}}
  # GET /api/admin/requests/{request_id}/message  (abuse.investigate, admin, AUDITED) -> {id, message}
  ```
  `AdminRequestOut` — **no `message` field at all**, not an empty one:
  ```jsonc
  { "id": "uuid", "buyer_name": "Dr. Rachel Mendes", "listing_title": "Small animal practice — Cedar Park",
    "listing_market": "Austin, TX", "seller_name": "Dr. James Whitfield",
    "status": "pending", "created_at": "…Z", "age_days": 6,
    "last_event": "created|accepted|declined|packet_released|message_viewed|null",
    "awaiting_seller": true }
  ```
  and `me_payload` gains `"license_state": str | None`. **Task 11's `admin/requests.ts` and Task 12's A43 entries read these verbatim.**

- [ ] **Step 1: Write the failing tests**

```python
def test_the_admin_queue_never_carries_message_content(staff_client, mixed_requests):
    for item in staff_client.get("/api/admin/requests").json()["items"]:
        assert "message" not in item, "the footer's promise is a schema fact, not a redaction"


def test_the_admin_queue_reports_age_and_whether_the_seller_is_still_holding_it(staff_client, old_pending_request):
    item = staff_client.get("/api/admin/requests").json()["items"][0]
    assert item["age_days"] >= 2 and item["awaiting_seller"] is True


def test_a_request_answered_inside_the_window_is_not_awaiting_the_seller(staff_client, accepted_request):
    assert staff_client.get("/api/admin/requests").json()["items"][0]["awaiting_seller"] is False


def test_the_age_sub_line_is_the_last_event_and_is_null_where_there_is_none(staff_client, accepted_request):
    assert staff_client.get("/api/admin/requests").json()["items"][0]["last_event"] == "packet_released"


def test_only_an_admin_may_read_a_message(staff_client, one_pending_request):
    assert staff_client.get(f"/api/admin/requests/{one_pending_request.id}/message").status_code == 403


def test_reading_a_message_needs_a_fresh_password(admin_client, one_pending_request):
    r = admin_client.get(f"/api/admin/requests/{one_pending_request.id}/message")
    assert r.status_code == 401 and r.json()["error"]["code"] == "REAUTH_REQUIRED"


def test_every_view_of_a_message_writes_one_audit_row_and_one_event(admin_reauthed_client, one_pending_request, audit_rows, events_of):
    r = admin_reauthed_client.get(f"/api/admin/requests/{one_pending_request.id}/message")
    assert r.status_code == 200 and r.json()["message"] == one_pending_request.message
    assert len([a for a in audit_rows() if a["action"] == "abuse.investigate"]) == 1
    assert events_of(one_pending_request.id)[-1]["kind"] == "message_viewed"


def test_two_views_write_two_rows(admin_reauthed_client, one_pending_request, audit_rows):
    for _ in range(2):
        admin_reauthed_client.get(f"/api/admin/requests/{one_pending_request.id}/message")
    assert len([a for a in audit_rows() if a["action"] == "abuse.investigate"]) == 2


def test_me_serves_the_license_state_from_the_latest_application(buyer_client_with_application):
    assert buyer_client_with_application.get("/api/me").json()["license_state"] == "NM"


def test_me_serves_a_null_license_state_where_no_application_recorded_one(buyer_client):
    assert buyer_client.get("/api/me").json()["license_state"] is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `poetry run pytest tests/api/test_requests.py tests/api/test_auth.py -q -k "admin_queue or message or license_state"`
Expected: 404s on the two routes; `KeyError: 'license_state'` on the two `/api/me` cases.

- [ ] **Step 3: Write the admin half**

```python
REQUIRE_OVERSEE = require("request.oversee")
REQUIRE_INVESTIGATE = require("abuse.investigate")
Overseer = Annotated[S.Principal, Depends(REQUIRE_OVERSEE)]
Investigator = Annotated[S.Principal, Depends(REQUIRE_INVESTIGATE)]

# `r.message` is NOT selected. The footer's promise — "Message contents are visible only in an abuse
# investigation, and every such view is logged" — is a schema fact here rather than a redaction the
# handler remembers to apply: a column that is never read cannot leak through a later change to the
# serialiser.
QUEUE_SQL = """
SELECT r.id, b.display_name, initcap(l.type) || ' practice — ' || l.city, l.market, s.display_name,
       r.status, r.created_at,
       (SELECT e.kind FROM request_event e WHERE e.request_id = r.id ORDER BY e.at DESC, e.id DESC LIMIT 1)
  FROM request r
  JOIN listing l ON l.id = r.listing_id
  LEFT JOIN account b ON b.id = r.buyer_account_id
  LEFT JOIN account s ON s.id = l.seller_id
 ORDER BY r.created_at DESC, r.id DESC
 LIMIT %s
"""


@router.get("/admin/requests", dependencies=[Depends(REQUIRE_OVERSEE)])
def admin_queue() -> dict[str, Any]:
    """Every request, with no message content at all.

    NOT audited: `request.oversee` is not in `AUDITED`, and one row per poll of the Requests tab
    into a table whose triggers refuse DELETE is the leak `users.review` was split out to avoid.
    The AUDITED act is reading a message, below."""
    now = datetime.now(UTC)
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute(QUEUE_SQL, (MAX_LIST,))
        rows = cur.fetchall()
        cur.execute("SELECT status, count(*) FROM request GROUP BY 1")
        grouped = dict(cast("list[tuple[str, int]]", cur.fetchall()))
    items = [{"id": str(r[0]), "buyer_name": r[1], "listing_title": r[2], "listing_market": r[3],
              "seller_name": r[4], "status": r[5], "created_at": r[6].isoformat(),
              "age_days": (now - r[6]).days, "last_event": r[7],
              # Spec §5's badge reading, and the design's own words for it: a request still pending
              # after AWAITING_HOURS is what "Awaiting seller" means.
              "awaiting_seller": r[5] == "pending" and now - r[6] >= timedelta(hours=AWAITING_HOURS)}
             for r in rows]
    return {"items": items, "counts": {s: grouped.get(s, 0) for s in STATUSES}}


@router.get("/admin/requests/{request_id}/message")
def admin_message(request_id: UUID, request: Request, principal: Investigator) -> JSONResponse:
    """One message, to an admin who has just confirmed their password, with the view recorded twice.

    `abuse.investigate` is admin-only and in `permissions.AUDITED`, so `audit.write(` is called in
    THIS body and never through a helper. The `request_event` row is the SECOND record and is not a
    duplicate of the first: `audit_log` is the tamper-evident ledger an auditor greps, and
    `request_event` is the timeline the admin Requests tab's own Age column reads — a buyer whose
    message was read three times shows it there.

    The audit row is written BEFORE the message is returned, and in the same transaction, so there
    is no state in which the content left the building without a trace."""
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT message FROM request WHERE id=%s", (request_id,))
        found = cur.fetchone()
        if found is None:
            return _error("NOT_FOUND", "No such request.", 404)
        audit.write(conn, actor=principal, action="abuse.investigate", target_type="request",
                    target_id=request_id, reason="message viewed", request=request)
        cur.execute("INSERT INTO request_event (request_id, actor_role, kind) VALUES (%s,%s,'message_viewed')",
                    (request_id, ",".join(sorted(principal.roles))))
    return JSONResponse({"id": str(request_id), "message": cast("tuple[str]", found)[0]})
```

- [ ] **Step 4: Serve `license_state` from `me_payload`**

In `app/api/auth.py`, extend `me_payload`'s existing single query rather than adding a second round trip (the `_email_of`/I11 pattern):

```python
        cur.execute("""SELECT a.id, a.email, a.display_name, a.state, a.affiliation_label,
                              (SELECT ap.fields ->> 'license_state' FROM application ap
                                WHERE ap.account_id = a.id AND ap.fields ? 'license_state'
                                ORDER BY ap.submitted_at DESC, ap.id DESC LIMIT 1)
                         FROM account a WHERE a.id=%s""", (principal.account_id,))
```
and add `"license_state": row[5]` to the returned dict. **`license_state` is the SELLER application's own field name** (`applications.SELLER_REQUIRED`); a buyer application does not collect one, so a buyer with no seller application reads `null` and the interest modal drops the row (spec §5). Do not invent a buyer field: if the VIN Foundation later collects one, it will use this same key and this query will find it.

- [ ] **Step 5: Carry it into the frontend `Me` type**

`frontend/src/auth/me.ts`: add `license_state: string | null` to the `Me` interface with a comment naming `app.api.auth.me_payload` as its source, and a `me.test.ts` case that a payload without the key reads `null` rather than `undefined` (the design's `sc-if` treats both as falsey, but the TYPE must not lie about what the server sends).

- [ ] **Step 6: Both gates, then commit**

```bash
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m "not timing"
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m timing -p no:randomly --cov-append --cov-report=xml --cov-fail-under=100
cd frontend && npm run typecheck && npm run build && npm test && cd ..
git add app/api/requests.py app/api/auth.py tests/api/test_requests.py tests/api/test_auth.py \
        frontend/src/auth/me.ts frontend/src/auth/me.test.ts docs/integrations/market-data-api.md
git commit -m "feat(requests): the staff queue with no message content, and the logged read

The admin queue never SELECTs r.message, so the Requests footer's promise is
a schema fact rather than a redaction. Reading one needs abuse.investigate,
a fresh password, and writes an audit row and a request_event before it
answers. /api/me gains license_state so the interest modal stops telling a
New Mexico buyer they are licensed in Texas.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 11: `requests/buyer.ts`, `requests/seller.ts`, `admin/requests.ts` (A43)

Three adapters, one per surface, in the M6 pattern. **No design file changes in this task.**

**Re-basing states: NONE.** **The thirteen frozen hashes must not move.**

**Files:**
- Create: `frontend/src/requests/buyer.ts` + `.test.ts`, `frontend/src/requests/seller.ts` + `.test.ts`, `frontend/src/admin/requests.ts` + `.test.ts`
- Modify: `frontend/src/app.setup.js` (three new app-only props)

**Interfaces:**
- Consumes: Tasks 8–10's routes; `admin/users.ts`'s `cell`, `A`, `Cell`, `ActionButton`; `auth/api.ts`'s `csrfToken`.
- Produces:
  ```ts
  // frontend/src/requests/buyer.ts
  export interface RequestOut { id: string; listing_id: string; listing_title: string; listing_market: string;
    seller_name: string | null; message: string; status: 'pending' | 'accepted' | 'declined';
    created_at: string; decided_at: string | null; reply: string | null; documents_released: boolean }
  export interface BuyerRequestsAdapter {
    create(listingId: string, message: string): Promise<void>;
    mine(): Promise<RequestOut[]>;
  }
  export function makeBuyerRequestsAdapter(): BuyerRequestsAdapter;

  // frontend/src/requests/seller.ts
  export interface SellerRequestOut extends RequestOut { buyer_name: string; buyer_role_label: string }
  export interface SellerRequestsAdapter {
    list(): Promise<SellerRequestOut[]>;
    decide(id: string, action: 'accept' | 'decline', reply: string): Promise<void>;
  }
  export function makeSellerRequestsAdapter(): SellerRequestsAdapter;

  // frontend/src/admin/requests.ts
  export interface AdminRequestOut { id: string; buyer_name: string; listing_title: string; listing_market: string;
    seller_name: string | null; status: string; created_at: string; age_days: number;
    last_event: string | null; awaiting_seller: boolean }
  /** `StepUp` is `src/admin/settings.ts`'s own interface, imported — there is ONE step-up shape. */
  export interface RequestsUi extends StepUp {
    show(title: string, body: string): void;
    mayInvestigate(): boolean;
  }
  export const REQUEST_PILLS: Record<string, { label: string; tone: string }>;
  export const EVENT_WORDS: Record<string, string | null>;
  /** The oracle-only arm (Task 13): a row the design's own `sets.activity` fixture produced, whose
   *  cells carry their own `pill`/`pillStyle` and action styles verbatim. `admin/listings.ts`'s
   *  `DesignListingRow` is the precedent and the shape. */
  export type DesignRequestRow = Cell[];
  export function toRequestRows(items: Array<AdminRequestOut | DesignRequestRow>, ui: RequestsUi): Cell[][];
  export function countAwaiting(items: AdminRequestOut[]): number;
  export interface AdminRequestsAdapter { list(): Promise<{ rows: Cell[][]; count: number }> }
  export function makeAdminRequestsAdapter(ui?: RequestsUi): AdminRequestsAdapter;
  ```
  **Task 12 reads `BuyerRequestsAdapter` and `SellerRequestsAdapter`; Task 13 reads `AdminRequestsAdapter`, `REQUEST_PILLS`, `countAwaiting` and `DesignRequestRow`.** The `DesignRequestRow` union arm is written in Task 13 with its own test, because that is where the oracle that needs it is built; the type is named here so Task 13's implementer does not invent a second name.

- [ ] **Step 1: Write the failing tests**

The three `.test.ts` files, each covering: the happy mapping; the refusal path (`throw` on a read, `ui.refuse` on a write); and the design-vocabulary assertions below, which are the reason these are mappings and not `fetch` calls:

```ts
// frontend/src/admin/requests.test.ts
it('uses the design’s own three pills and never invents a fourth', () => {
  expect(Object.keys(REQUEST_PILLS).sort()).toEqual(['accepted', 'declined', 'pending']);
  expect(REQUEST_PILLS.pending.label).toBe('Awaiting seller');
  expect(REQUEST_PILLS.accepted.label).toBe('Engaged');
  expect(REQUEST_PILLS.declined.label).toBe('Declined');
});

it('omits the Request column’s paraphrase sub-line — staff never see content (spec §5)', () => {
  const row = toRequestRows([QUEUE_ROW], ui())[0];
  expect(row[0].main).toBe('Dr. Rachel Mendes');
  expect(row[0].hasSub, 'the design’s "Asked for a phased transition plan" is a paraphrase of a message').toBe(false);
});

it('puts the last event under the age, and nothing where there is none', () => {
  expect(toRequestRows([{ ...QUEUE_ROW, last_event: 'packet_released' }], ui())[0][3].sub).toBe('Packet released');
  expect(toRequestRows([{ ...QUEUE_ROW, last_event: null }], ui())[0][3].hasSub).toBe(false);
});

it('offers Open message (logged) only to an abuse.investigate holder', () => {
  expect(toRequestRows([QUEUE_ROW], ui({ mayInvestigate: false }))[0][3].hasActions).toBe(false);
  expect(toRequestRows([QUEUE_ROW], ui({ mayInvestigate: true }))[0][3].actions.map((a) => a.label))
    .toEqual(['Open message (logged)']);
});

it('reads a message only after the step-up, and shows it in the dialog the design already has', async () => {
  const u = ui({ mayInvestigate: true, fetchBody: { message: 'Phased transition?' } });
  await toRequestRows([QUEUE_ROW], u)[0][3].actions[0].go();
  expect(u.calls).toEqual(['stepUp:abuse.investigate:Open message (logged):no-note', 'show:Request message:Phased transition?']);
});

it('counts the requests awaiting a seller — the badge the design draws "2" for', () => {
  expect(countAwaiting([{ ...QUEUE_ROW, awaiting_seller: true }, { ...QUEUE_ROW, awaiting_seller: false }])).toBe(1);
});
```

`EVENT_WORDS` is decision D6's table and is one literal: `{ created: null, accepted: 'Seller engaged', declined: 'Seller declined', packet_released: 'Packet released', message_viewed: 'Message viewed by staff' }`. A `created` event yields NO sub-line — "a request was created" is what the row already says. A kind the table does not carry prints its own key, the `admin/data_sources.ts` rule.

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/requests src/admin/requests.test.ts`
Expected: FAIL — `Failed to resolve import`.

- [ ] **Step 3: Write the three modules**

Each carries a module docstring naming its route, its design surface and the ONE thing it refuses to invent (the paraphrase sub-line, the "Review" pill, the reminder). `toRequestRows` produces the four cells the design's `sets.activity` grid expects — **Request · Practice · Status · Age** — and the pill tones are the design's own (`warn` for pending, `ok` for accepted, `bad` for declined), read off `logic.js`'s own `sets.activity` rows rather than typed:

```bash
python3 -c "import pathlib;s=pathlib.Path('frontend/src/logic.js').read_text();i=s.find('activity: {');print(s[i:i+1200])"
```

- [ ] **Step 4: Declare the three props**

`frontend/src/app.setup.js`, beside `adminSettings`:
```js
  requests: { type: Object, default: () => makeBuyerRequestsAdapter() },
  sellerRequests: { type: Object, default: () => makeSellerRequestsAdapter() },
  adminRequests: { type: Object, default: () => makeAdminRequestsAdapter(requestsUi()) },
```
`requestsUi()` routes `stepUp` through `window.__pmStepUp` (Task 4 Step 5's seam), `show` through a new `window.__pmShowMessage` the design sets in `componentDidMount` (Task 13's A43 entry), `refuse` through `window.alert`, and `mayInvestigate` through `makePermsAdapter().allowed('abuse.investigate')`.

- [ ] **Step 5: Gate and commit**

```bash
cd frontend && npm run typecheck && npm run build && npm test
git add frontend/src/requests frontend/src/admin/requests.ts frontend/src/admin/requests.test.ts frontend/src/app.setup.js
git commit -m "feat(requests): the three adapters — buyer, seller, staff

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 12: The three member surfaces — A43.1–A43.9 (design)

The interest modal's submit, My Requests and the seller inbox stop writing to `state.requests` and start speaking to the API. **`state.requests` stays in the script**, per CLAUDE.md's launch-removal rule — it is the D6 stub's own source and the reference's fixture path.

**Re-basing states: ZERO re-based.** `requests` and `seller-dash` are TWO OF THE FROZEN THIRTEEN, so **A43.1–A43.9 must not move either hash**: every entry is A16.1's ternary keyed on adapter PRESENCE, the reference passes no adapter, and the design's own fixtures render exactly as before. **This is the highest-risk task in the plan for the frozen set. Measure after every entry, not once at the end.**

**Files:** `frontend/tests/design-amendments.ts` + `.test.ts`, `frontend/src/logic.test.ts`, regenerated bundle files.

**Interfaces:** consumes Task 11's `BuyerRequestsAdapter`, `SellerRequestsAdapter` and `RequestOut`; produces the design's `state.myRequests` and `state.sellerInbox` (both `undefined` until loaded) and `state.interestErr` (`""`, the modal's own refusal slot — A43.7 declares all three), plus `loadRequests()` and `reloadInbox()` beside A16.17's `reloadListings`.

- [ ] **Step 1: Print and count the nine anchors**

```bash
python3 - <<'PY'
import pathlib
s = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html").read_text(encoding="utf-8")
anchors = {
 "A43.1 modal.shared": '          { k: "License state", v: "Texas" },\n          { k: "VIN Foundation status", v: "Approved buyer" }\n',
 "A43.2 sendInterest": '      sendInterest: () => {\n',
 "A43.3 reqList":      '      reqList: s.requests.map((r) => {\n',
 "A43.4 noRequests":   '      noRequests: s.requests.length === 0,\n',
 "A43.5 inbox filter": '    const inbox = s.requests.filter((r) => r.pid === "p1" || r.pid === "p7" || r.pid === "p6");\n',
 "A43.6 inbox map":    '      inbox: inbox.map((r) => {\n',
}
for k, v in anchors.items():
    print(k, s.count(v))
PY
```
Expected: `1` each. The three remaining entries (A43.7 the state keys, A43.8 the loaders, A43.9 `componentDidMount`) anchor on Task 3's A41.3 output, A16.17's `reloadListings` and A40.4's `this.loadAdmin();` respectively — print and count those the same way, and declare each `Consumes`.

- [ ] **Step 2: Write the failing structural test**

```ts
describe('A43 — the three member request surfaces', () => {
  const amended = readFileSync(AMENDED, 'utf8');

  it('serves the interest modal’s two literals, and drops a row the API did not answer', () => {
    expect(amended).not.toContain('{ k: "License state", v: "Texas" }');
    expect(amended).toContain('me.licenseState ? [{ k: "License state", v: me.licenseState }] : []');
    expect(amended).toContain('me.role ? [{ k: "VIN Foundation status", v: me.role }] : []');
  });

  it('sends the request through the adapter, and keeps the design’s own fixture path without one', () => {
    expect(amended).toContain('if (!this.props.requests) {');
    expect(amended).toContain('this.props.requests.create(s.detailId, s.interestMsg)');
  });

  it('renders the loaded requests or NO rows, never the fixture, once an adapter is present', () => {
    expect(amended).toContain('(s.myRequests !== undefined ? s.myRequests : (this.props.requests ? [] : s.requests))');
  });

  it('renders the seller’s OWN inbox rather than a three-listing id filter', () => {
    expect(amended).toContain('(s.sellerInbox !== undefined ? s.sellerInbox : (this.props.sellerRequests ? [] : s.requests.filter((r) => r.pid === "p1" || r.pid === "p7" || r.pid === "p6")))');
  });

  it('accepts and declines through the API, and says what the accept released', () => {
    expect(amended).toContain('this.props.sellerRequests.decide(r.id, "accept"');
    expect(amended).toContain('You released the financial packet and floor plan to this buyer.');
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd frontend && npx vitest run tests/design-amendments.test.ts -t 'member request surfaces'`
Expected: FAIL on the first `not.toContain` (the literal is still there).

- [ ] **Step 4: Write the nine entries**

Each is A16.1's shape. The two that need spelling out in full because they are not a ternary:

```ts
// A43.2 — the interest modal's submit. With no adapter the design's own fixture path runs
// UNCHANGED, byte for byte, which is what keeps `detail` and `interest-modal` where they are; with
// one, the request goes to POST /api/requests and the modal reaches its "sent" state only when the
// route answered. A refusal leaves the modal OPEN on its own error slot rather than claiming a
// request nobody received (spec §1 rule 3).
      sendInterest: () => {
        if (!s.interestMsg.trim()) return this.setState({ interest: "error" });
        if (!this.props.requests) {
          const p = P.filter((x) => x.id === s.detailId)[0];
          return this.setState({
            interest: "sent",
            sent: s.sent.concat([s.detailId]),
            requests: [{ id: "n" + Date.now(), pid: s.detailId, buyer: s.me.name, status: "pending", when: "Today", msg: s.interestMsg }].concat(s.requests)
          });
        }
        return this.props.requests.create(s.detailId, s.interestMsg).then(
          () => { this.setState({ interest: "sent", sent: s.sent.concat([s.detailId]) }); return this.loadRequests(); },
          (e) => this.setState({ interest: "error", interestErr: (e && e.message) || "That request could not be sent." })
        );
      },
```
**Note the unused `const p` in the fixture arm** — it is the design's own line and is kept byte for byte; if the pristine bundle does not declare it, do not add it. Print the arm before writing:
```bash
python3 -c "import pathlib;s=pathlib.Path('docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html').read_text(encoding='utf-8');i=s.find('      sendInterest: () => {');print(s[i:i+700])"
```

```ts
// A43.8 — the two loaders, beside A16.17's `reloadListings`. Each has its own rejection arm, which
// leaves the surface EMPTY rather than back on the design's fixtures (A16.17's discipline).
// Consumes A16.17.
  loadRequests() {
    if (!this.props.requests) return Promise.resolve([]);
    return this.props.requests.mine().then((rows) => this.setState({ myRequests: rows }), () => this.setState({ myRequests: [] }));
  }

  reloadInbox() {
    if (!this.props.sellerRequests) return Promise.resolve([]);
    return this.props.sellerRequests.list().then((rows) => this.setState({ sellerInbox: rows }), () => this.setState({ sellerInbox: [] }));
  }
```

A43.3 and A43.6 map a `RequestOut` onto the design's own card shape. **The labels, the tones, the hints and `resolvedNote` are the design's own strings and are not retyped** — extract each map body first and edit only the source of its fields (`r.status` is unchanged; `p.type + " practice — " + p.area` becomes `r.listingTitle` where a served row is present, and the fixture arm keeps `P.filter(...)`).

- [ ] **Step 5: Regenerate, characterise, and MEASURE the two frozen rows**

```bash
cd frontend && npm run gen:design && npm run gen:logic && npm run gen:app
npm run typecheck && npm run build && npm test
npm run test:visual:baselines && npm run test:e2e
```
then **C6 of the closing sequence** with `PRE="$SCRATCH/a43-baselines-before.json"`.

**Expected: `0 moved`.** `requests` or `seller-dash` moving means an entry changed the fixture path: stop with NEEDS_CONTEXT and bisect entry by entry (`git stash` is forbidden — comment the entry out of `amendments()`, regenerate, re-measure, restore).

`frontend/src/logic.test.ts`, `describe('A43 — the member surfaces')`: with no adapter every one of the three surfaces renders the design's fixtures unchanged (compare against a pre-A43 snapshot of `renderVals()` held in the test as a literal); with an adapter and no loaded rows, each renders NONE; a failed `create` leaves `interest` on `"error"` and the modal open; a failed `decide` leaves the row pending.

- [ ] **Step 6: Commit**

```bash
git add frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts frontend/src/logic.test.ts \
        "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
        frontend/src/logic.js frontend/src/App.vue frontend/src/generated/pseudo.css
git commit -m "feat(design): A43.1-A43.9 — the buyer asks, the seller answers, for real

The interest modal, My Requests and the seller inbox stop writing to an
in-memory array. The two modal literals are served, so a New Mexico buyer is
no longer told they are licensed in Texas.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 13: The admin Requests tab — A43.10–A43.14, and the ledger (A43)

**Re-basing states: ZERO re-based, ONE appended.** `admin-requests` **is one of the frozen thirteen** and must not move: A43.10 is A17.1's ternary, the oracle answers `GET /api/admin/requests` with the design's own four rows through a `DesignRequestRow` arm, and the reference passes no adapter.

**Files:** `frontend/tests/design-amendments.ts` + `.test.ts`, `frontend/src/logic.test.ts`, `frontend/tests/harness.ts` + `.test.ts`, `frontend/tests/design-admin-requests.mjs` (create), `frontend/tests/smoke.spec.ts`, `LOCAL_AMENDMENTS.md`, `CLAUDE.md`, regenerated bundle files.

**Interfaces:** consumes Task 11's `AdminRequestsAdapter.list(): Promise<{rows, count}>`, `REQUEST_PILLS`; produces the `window.__pmShowMessage` seam and `state.adminRequestRows`/`adminRequestCount`.

- [ ] **Step 1: Print and count the five anchors, then write the failing structural test**

Anchors: `sets.activity.rows` (the four-row literal, printed by Step 1 of Task 12's command pointed at `'      activity: {'`), the `activity` tab's `count: "2"` (A43.11), Task 3's state line (A43.12, `Consumes A41.3`), A41.4's `loadAdmin` body (A43.13, `Consumes A41.4`), and A41.11's `componentDidMount` (A43.14, the `window.__pmShowMessage` seam, `Consumes A41.11`).

```ts
describe('A43 — the admin Requests tab', () => {
  const amended = readFileSync(AMENDED, 'utf8');
  it('renders the loaded queue or NO rows, never the design’s four fixtures', () => {
    expect(amended).toContain('rows: s.adminRequestRows !== undefined ? s.adminRequestRows : (this.props.adminRequests ? [] : [');
  });
  it('takes the badge from the requests awaiting a seller, and keeps the design’s "2" without an adapter', () => {
    expect(amended).toContain('{ key: "activity", label: "Requests", count: s.adminRequestCount !== undefined ? String(s.adminRequestCount) : (this.props.adminRequests ? null : "2") }');
  });
  it('mounts the message viewer the adapter shows a message through, and removes it', () => {
    expect(amended).toContain('window.__pmShowMessage = (title, body) =>');
    expect(amended).toContain('window.__pmShowMessage = null;');
  });
});
```

- [ ] **Step 2: Run it to verify it fails** — `npx vitest run tests/design-amendments.test.ts -t 'admin Requests tab'` → FAIL on the first `toContain`.

- [ ] **Step 3: Write the five entries**

A43.14's viewer is **the re-authentication dialog's own box, reused read-only**: rather than a second modal, `window.__pmShowMessage(title, body)` sets `reauthOpen: null` and a new `viewer: { title, body }` state key that mounts the SAME box (A41.8's markup) with the password field, the note field and the Confirm button unmounted and one `<p>` in the interest modal's own `isSent` paragraph declarations. That is one element serving two states, which is the design's own idiom for the interest modal (`isForm`/`isSent`). Extract the `isSent` paragraph before writing:
```bash
python3 -c "import pathlib;s=pathlib.Path('docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html').read_text(encoding='utf-8');i=s.find('Your request has gone to the seller');print(s[i-500:i+400])"
```

- [ ] **Step 4: Give the tab its oracle**

`frontend/tests/design-admin-requests.mjs` — derived from `adminVals()`'s own `sets.activity`, exactly as `design-admin-listings.mjs` is derived: it exports the design's FOUR rows in `DesignRequestRow` shape, **the "Review" row included**, because that row's status backs no `request.status` value and inventing one is out of scope — a limit on the LIVE mapping's `REQUEST_PILLS`, never on this oracle-only fixture (the A17 rule, restated here because it applies identically). `harness.ts` answers `GET /api/admin/requests` with it; `harness.test.ts` pins the stub.

`toRequestRows` must therefore read either an `AdminRequestOut` or a `DesignRequestRow`, the union `admin/listings.ts` already carries — **add the union arm to Task 11's module in this task, with its own test**, and copy the design row's `pill`/`pillStyle` and action styles verbatim rather than deriving them from `REQUEST_PILLS`.

- [ ] **Step 5: The appended state, in `smoke.spec.ts` only**

`admin-requests-message` — the tab, the Open message button, the step-up, and the message in the box. App only, Task 5 Step 4's limitation.

- [ ] **Step 6: Run the closing sequence, C1 to C6**

Fourteen ledger rows — A43.1-A43.14 — with `Consumes A16.17` on A43.8's, `Consumes A41.3` on A43.12's, `Consumes A41.4` on A43.13's and `Consumes A41.11` on A43.14's. **C6's expected MOVED list is EMPTY — `admin-requests`, `requests` and `seller-dash` in particular.**

- [ ] **Step 7: Commit and hand back**

```bash
git add frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts frontend/src/logic.test.ts \
        frontend/src/admin/requests.ts frontend/src/admin/requests.test.ts \
        frontend/tests/harness.ts frontend/tests/harness.test.ts frontend/tests/design-admin-requests.mjs \
        frontend/tests/smoke.spec.ts "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
        frontend/src/logic.js frontend/src/App.vue frontend/src/generated/pseudo.css \
        docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md CLAUDE.md
git commit -m "feat(design): A43.10-A43.14 — the admin Requests tab reads the real queue

No message content reaches the tab; Open message (logged) is admin-only,
re-authenticated, and writes an audit row and a request_event per view —
which is what the design's own footer has promised since V3.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

Hand back: base and final SHAs, the hash diff, the fourteen A43 entry ids, the migration number used (094), and the three routes' contract-doc rows.

---

## Task 14: `admin/user_detail.ts` (A44)

`GET /api/admin/users/{id}` (audited, `users.view_detail`), `POST /api/admin/users/{id}/grants` (`roles.grant`, REAUTH, AUDITED) and `GET /api/admin/audit` have been complete since Task I5 and are **reachable by nothing**. This is their adapter.

**Re-basing states: NONE.** **The thirteen frozen hashes must not move.**

**Files:** create `frontend/src/admin/user_detail.ts` + `.test.ts`; modify `frontend/src/app.setup.js`.

**Interfaces:**
- Consumes: the three routes above (read them: `sed -n '470,510p' app/api/admin_users.py` for the detail payload, `sed -n '628,678p'` for grants, `sed -n '727,740p'` for audit); `admin/users.ts`'s `cell`, `A`, `Cell`; A41's step-up seam.
- Produces:
  ```ts
  /** Exactly what `GET /api/admin/audit` answers (`app.api.admin_users.audit_read`). Task 20
   *  imports this type rather than declaring a second one. */
  export interface AuditRow { id: number; at: string; actor_id: string | null; actor_role: string | null;
    action: string; target_type: string; target_id: string | null;
    before: unknown; after: unknown; reason: string | null }
  export interface Grant { role: string; granted_by: string | null; granted_by_name: string | null; granted_at: string }
  export interface ApplicationRow { id: string; kind: string; fields: Record<string, unknown>; flags: string[];
    status: string; submitted_at: string; decided_at: string | null; decision_note: string | null;
    info_request: string | null; answer: string | null; answered_at: string | null;
    resubmitted_at: string | null; decision: string | null }
  export interface UserDetail {
    account: { id: string; email: string; state: string; name: string | null; affiliation_label: string | null;
               created_at: string; last_sign_in_at: string | null };
    application: ApplicationRow | null; application_history: ApplicationRow[];
    roles: string[]; grants: Grant[];
  }
  /** `StepUp` is `src/admin/settings.ts`'s own interface, imported — there is ONE step-up shape. */
  export interface DetailUi extends StepUp { mayGrant(): boolean }
  export const DETAIL_TABS: readonly string[];       // ['Overview', 'History', 'Access']
  export interface DetailPanel {
    title: string; subtitle: string; tabs: Array<{ key: string; label: string; on: boolean; go: () => void }>;
    facts: Array<{ k: string; v: string }>;
    rows: Cell[][];                                   // the active tab's rows, in the table idiom
  }
  export function toUserDetail(detail: UserDetail, auditRows: AuditRow[], tab: string, ui: DetailUi,
                               grant: (role: string, on: boolean) => Promise<void>): DetailPanel;
  export interface AdminUserDetailAdapter {
    open(accountId: string): Promise<UserDetail>;
    audit(accountId: string): Promise<AuditRow[]>;
    grant(accountId: string, role: string, on: boolean): Promise<void>;
  }
  export function makeAdminUserDetailAdapter(ui?: DetailUi): AdminUserDetailAdapter;
  ```
  **Task 15 reads `DETAIL_TABS`, `DetailPanel` and `AdminUserDetailAdapter`; Task 16 reads `grant` and `mayGrant`; Task 20's `admin/listing_detail.ts` copies `DetailPanel` shape exactly, with `DETAIL_TABS` of two.**

- [ ] **Step 1: Write the failing tests** — one per fact the panel shows, driving `toUserDetail` with a real-shaped payload read off `tests/api/test_admin_users.py`'s own fixtures:

```ts
it('heads the panel with the applicant and their state, the docked panel’s own title/subtitle pair', () => { … });
it('puts the application fields on Overview, in the order the API returned them', () => { … });
it('puts every decision on History with its decider’s NAME and date, never a uuid', () => { … });
it('puts the audit rows for THIS target on History, newest first', () => { … });
it('lists each grant with who granted it and when', () => { … });
it('offers Grant role / Revoke role only to a roles.grant holder', () => { … });
it('routes a grant through the step-up, because roles.grant is in REAUTH', () => { … });
it('renders an account with no application at all without inventing one', () => { … });
it('renders an empty audit answer as no rows rather than as a failure', () => { … });
```

- [ ] **Step 2: Run them to verify they fail** — `Failed to resolve import "./user_detail"`.

- [ ] **Step 3: Write the module.** The `audit` read filters client-side by `target_id`, because `GET /api/admin/audit` takes only `limit` — **record that in the module docstring as a known cost** (`MAX_AUDIT` is 500, so a busy trail can push an old row for this account off the page) and do NOT add a server filter in this task: widening a published contract is its own change with its own review.

- [ ] **Step 4: Declare the prop** — `adminUserDetail: { type: Object, default: () => makeAdminUserDetailAdapter(detailUi()) }`.

- [ ] **Step 5: Gate and commit**

```bash
cd frontend && npm run typecheck && npm run build && npm test
git add frontend/src/admin/user_detail.ts frontend/src/admin/user_detail.test.ts frontend/src/app.setup.js
git commit -m "feat(admin): the user drill-down's adapter — three routes nothing could reach

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 15: The drill-down panel and its Overview/History tabs — A44.1–A44.6 (design)

V3 has ONE detail idiom and it is the Browse docked panel: a 366 px right-hand column with a `PRACTICE DETAIL` kicker, a 38 px close, a tab row and a scrolling body. The admin drill-down is that panel, anchored right inside the admin shell (decision D7 — **not a route**, so `frontend/src/router/sync.ts` is untouched and the admin URL does not move).

**Re-basing states: ZERO re-based while closed.** `admin-users` is frozen; the panel is one unmounted `sc-if`. **Measure.** One state appended in Task 16.

**Files:** `frontend/tests/design-amendments.ts` + `.test.ts`, `frontend/src/logic.test.ts`, regenerated bundle files.

**Interfaces:** consumes Task 14's `DetailPanel`, `DETAIL_TABS`, `AdminUserDetailAdapter`; produces `state.detailPanel` (`null` | `{ kind: 'user' | 'listing', id, tab }`), `openDetailPanel(kind, id)`, `closeDetailPanel()`, `setDetailTab(key)`, and the render value `admin.panel`. **Task 21 reuses all five for `kind: 'listing'` and adds no new state key.**

- [ ] **Step 1: Extract the docked panel's own declarations**

```bash
python3 - <<'PY'
import pathlib
s = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html").read_text(encoding="utf-8")
i = s.find('Practice detail')
print("--- the panel shell (kicker, close, column) ---")
print(s[i-900:i+700])
j = s.find('md.panel.tabs')
print("--- the panel's tab row ---")
print(s[max(0,j-700):j+700])
PY
```
**Every style string in A44.3's markup is pasted from that output.** The kicker's text becomes `{{ admin.panel.kicker }}` (`"USER DETAIL"` / `"LISTING DETAIL"`), which is a data substitution in an element V3 already has, not a new element.

- [ ] **Step 2: Write the failing structural test**

```ts
describe('A44 — the admin drill-down', () => {
  const amended = readFileSync(AMENDED, 'utf8');
  it('is the docked panel’s own column, kicker and close control', () => {
    expect(amended).toContain('width: 366px; flex: none; overflow-y: auto; border-left: 1px solid #e6e6e6; background: var(--vf-white); animation: rf-slide-in 300ms var(--easing-out) both;');
    expect(amended).toContain('{{ admin.panel.kicker }}');
  });
  it('opens from a row click and is closed by default', () => {
    expect(amended).toContain('openDetailPanel("user", ');
    expect(amended).toContain('detailPanel: null,');
  });
  it('adds NO route — the admin screen keeps its URL', () => {
    expect(amended).not.toContain('screen: "admin-user"');
  });
  it('renders what the adapter answered, or nothing', () => {
    expect(amended).toContain('s.detailData !== undefined ? s.detailData : null');
  });
});
```

- [ ] **Step 3: Run it to verify it fails.** — FAIL on `{{ admin.panel.kicker }}`.

- [ ] **Step 4: Write the six entries**

**A44.1** the state keys (`detailPanel`, `detailData`, `detailAudit`, `detailErr`), **A44.2** the four class members, **A44.3** the markup (the panel, inside the admin screen's own flex row so it docks right exactly as Browse's does), **A44.4** the render value `admin.panel`, **A44.5** the row click on Users — `admin/users.ts`'s `toUserRows` gains an `open` on the first cell, and the design's `sets.<tab>.rows` mapping passes it through — and **A44.6** Escape/outside-click closing it through A41.9/A41.10's shared closures, adding **no listener**.

**A44.5 is the one entry that can move `admin-users`.** A clickable first cell must paint identically to a non-clickable one: the `cursor: pointer` goes on the ROW's existing style string (which the design already composes per row), no underline, no colour change, no new element. If a measurement shows the hash moved, the click target is wrong — stop, do not re-pin.

- [ ] **Step 5: Regenerate, characterise, measure**

`logic.test.ts`: the panel is closed by default; a row click opens it and calls `open(id)` exactly once; a rejected `open` sets `detailErr` and leaves the panel closed (a panel with an error and no data is a lie about a user); the tab row switches without re-fetching the detail; Escape closes it; closing clears `detailData` so a second open cannot show the previous user for a frame.

Then the hash diff. **Expected: nothing.**

- [ ] **Step 6: Commit**

```bash
git add frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts frontend/src/logic.test.ts \
        frontend/src/admin/users.ts frontend/src/admin/users.test.ts \
        "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
        frontend/src/logic.js frontend/src/App.vue frontend/src/generated/pseudo.css
git commit -m "feat(design): A44.1-A44.6 — the admin drill-down, in the docked panel's own idiom

Three routes complete since Task I5 and reachable by nothing now have a
screen: the user detail, its history and the audit rows for that target. It
is an sc-if inside the admin shell, not a route, so the admin URL does not
move and the four frozen admin captures keep their pixels while it is closed.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 16: The Access tab and the role grant — A44.7–A44.10, and the ledger (A44)

**Re-basing states: ZERO re-based, ONE appended** (`admin-user-access`, app only, `smoke.spec.ts`). **`admin-users` must not move.**

**Files:** as Task 15, plus `frontend/tests/smoke.spec.ts`, `LOCAL_AMENDMENTS.md`, `CLAUDE.md`.

**Interfaces:** consumes Task 14's `grant`, `mayGrant`, `DETAIL_TABS`; A41's `openReauth(perm, label, run, note)` with `note: null` (ruling: a grant's reason rides in the audit row's `after`, and `POST /api/admin/users/{id}/grants` takes no note — **do not invent a field the route discards**).

- [ ] **Step 1: Write the failing real-browser case**

```ts
test('granting a role asks for the password first, and the grant shows its granter', async ({ page }) => {
  await reach(page, { screen: 'admin', persona: 'design' });
  await page.getByText('Dr. Rachel Mendes').first().click();
  await expect(page.getByText('USER DETAIL')).toBeVisible();
  await click(page, 'Access');
  await expect(page.getByText(/granted .* by /)).toBeVisible();
  await page.getByRole('button', { name: 'Grant role' }).click();
  await expect(page.getByText('Confirm your password to continue')).toBeVisible();
});
```

- [ ] **Step 2: Run it to verify it fails** — the Access tab has no rows yet.

- [ ] **Step 3: Write the four entries** — **A44.7** the Access tab's rows (`DETAIL_TABS`'s third entry becomes reachable), **A44.8** the Grant role / Revoke role pair, drawn only for a `roles.grant` holder, **A44.9** the step-up wrapper, **A44.10** the refresh after a grant the API accepted (re-`open(id)`, not a whole-tab reload — the panel is what changed).

- [ ] **Step 4: Run the closing sequence, C1 to C7.** Ten ledger rows, A44.1-A44.10. **C6's expected MOVED list is EMPTY** and its APPENDED list is empty (`admin-user-access` is a `smoke.spec.ts` case). The hand-back also carries the `GET /api/admin/audit` client-side-filter cost recorded in Task 14 Step 3.

---

## Task 17: `GET /api/admin/tokens` (A46)

`POST /api/admin/tokens` mints and `POST /api/admin/tokens/{id}/revoke` revokes; **there is no list route**, so Settings' "Manage" would open onto nothing. This builds it.

**Re-basing states: NONE.** **The thirteen frozen hashes must not move.**

**Files:** modify `app/api/admin_users.py` (the route, beside `create_token`), `tests/api/test_admin_users.py`, `docs/integrations/market-data-api.md`.

**Interfaces:**
- Consumes: `migrations/012_api_tokens.sql`'s columns — `id, name, role, created_by, created_at, expires_at, revoked_at, last_used_at`; `TokenManager`.
- Produces:
  ```python
  # GET /api/admin/tokens  (tokens.manage — admin, REAUTH)  -> {"items": [TokenOut]}
  ```
  ```jsonc
  { "id": "uuid", "name": "k6-qa", "role": "buyer", "created_by_name": "Jane Ops|null",
    "created_at": "…Z", "expires_at": "…Z", "revoked_at": "…Z|null", "last_used_at": "…Z|null",
    "live": true }
  ```
  `live` is `revoked_at IS NULL AND expires_at > now()` — computed in SQL, because "live" is what the Settings row's count means and a client that recomputed it could disagree with the server about a token expiring this second. **`token_hash` is never selected.** Task 18's `admin/tokens.ts` types this verbatim.

- [ ] **Step 1: Write the failing tests**

```python
def test_the_token_list_never_carries_a_hash(admin_reauthed_client, three_tokens):
    for item in admin_reauthed_client.get("/api/admin/tokens").json()["items"]:
        assert "token_hash" not in item and "token" not in item


def test_it_lists_revoked_and_expired_tokens_too_and_marks_them_not_live(admin_reauthed_client, three_tokens):
    items = {i["name"]: i for i in admin_reauthed_client.get("/api/admin/tokens").json()["items"]}
    assert items["live-one"]["live"] is True
    assert items["revoked-one"]["live"] is False
    assert items["expired-one"]["live"] is False


def test_it_names_the_minter_rather_than_their_uuid(admin_reauthed_client, three_tokens):
    assert admin_reauthed_client.get("/api/admin/tokens").json()["items"][0]["created_by_name"] is not None


def test_listing_tokens_needs_a_fresh_password(admin_client):
    r = admin_client.get("/api/admin/tokens")
    assert r.status_code == 401 and r.json()["error"]["code"] == "REAUTH_REQUIRED"


def test_an_api_token_can_never_list_tokens(admin_token_client):
    assert admin_token_client.get("/api/admin/tokens").status_code == 401


def test_staff_cannot_list_tokens(staff_reauthed_client):
    assert staff_reauthed_client.get("/api/admin/tokens").status_code == 403
```

- [ ] **Step 2: Run them to verify they fail** — `assert 404 == 200` on the first four.

- [ ] **Step 3: Write the route**

```python
TOKENS_SQL = """
SELECT t.id, t.name, t.role, c.display_name, t.created_at, t.expires_at, t.revoked_at, t.last_used_at,
       (t.revoked_at IS NULL AND t.expires_at > now())
  FROM api_token t LEFT JOIN account c ON c.id = t.created_by
 ORDER BY t.created_at DESC, t.id DESC
 LIMIT %s
"""


@router.get("/tokens")
async def list_tokens(principal: TokenManager) -> dict[str, Any]:
    """Every automation token, live or not — a revoked one is the row an auditor most wants.

    `token_hash` is NEVER selected: the secret half is stored hashed and shown once at mint
    (`app.auth.tokens`), and a column that is never read cannot leak through a later change to the
    serialiser (the `admin/requests` rule).

    `live` is computed in SQL rather than by the caller: it is what the Settings row's count means,
    and a client recomputing it from `expires_at` could disagree with the server about a token
    expiring this second.

    `tokens.manage` is in REAUTH, so listing tokens costs a password — which is why the Settings
    row shows no count until Manage has been opened (controller decision D5): a screen must not
    demand a password to paint. NOT audited: `tokens.manage` IS in `AUDITED`, and the mint and the
    revoke each write their own row from their own body; a LIST that wrote one would put a row in
    an append-only table every time the panel refreshed. The reachability of this read is already
    bounded by the ten-minute re-auth window."""
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute(TOKENS_SQL, (MAX_LIST,))
        return {"items": [{"id": str(r[0]), "name": r[1], "role": r[2], "created_by_name": r[3],
                           "created_at": r[4].isoformat(), "expires_at": r[5].isoformat(),
                           "revoked_at": _iso(r[6]), "last_used_at": _iso(r[7]), "live": r[8]}
                          for r in cur.fetchall()]}
```

**Read `tests/auth/test_permissions.py::test_audited_permissions_are_written_by_their_handlers` before committing.** `tokens.manage` is in `AUDITED` and this handler writes no row; if that test asserts *every route carrying an audited permission writes one*, this route breaks it and the correct fix is to name the exemption in the test with the reason above — **not** to write a row per poll. If it instead asserts *every audited ACTION is written by some handler*, nothing changes. Check which, and say which in the hand-back.

- [ ] **Step 4: Both gates, doc the route, commit**

```bash
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m "not timing"
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m timing -p no:randomly --cov-append --cov-report=xml --cov-fail-under=100
git add app/api/admin_users.py tests/api/test_admin_users.py tests/auth/test_permissions.py docs/integrations/market-data-api.md
git commit -m "feat(admin): GET /api/admin/tokens — the list Manage opens onto

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 18: `admin/tokens.ts` and the matrix view's layout (A46)

`frontend/src/admin/permissions.ts` already maps `GET /api/admin/permissions` into `cell()` rows and deliberately computes **no grid and no `headStyle`**, because "the design has no Permissions tab yet". It has one now.

**Re-basing states: NONE.** **The thirteen frozen hashes must not move.**

**Files:** create `frontend/src/admin/tokens.ts` + `.test.ts`; modify `frontend/src/admin/permissions.ts` + `.test.ts`, `frontend/src/app.setup.js`.

**Interfaces:**
- Consumes: Task 17's `GET /api/admin/tokens`; `GET /api/admin/permissions`'s `{roles, matrix, reauth, audited, token_denied, token_never_reauth}`; A41's step-up seam; `admin/users.ts`'s `cell`/`A`.
- Produces:
  ```ts
  // frontend/src/admin/tokens.ts
  export interface TokenOut { id: string; name: string; role: string; created_by_name: string | null;
    created_at: string; expires_at: string; revoked_at: string | null; last_used_at: string | null; live: boolean }
  /** Spec §6 names four facts — name, created, last used, Revoke. They render as the Users tab's
   *  own FOUR-COLUMN `cell(main, sub, pill, tone, actions)` shape, which is a main line and a
   *  sub-line per column: `Token` carries the name over `created <Month Year> by <minter>`, and
   *  `Status` carries the pill over `last used <Month Year>` / `never used`. Four facts, four
   *  columns, no invented column width — the design has no five-column admin table. */
  export const TOKEN_COLUMNS: readonly string[];   // ['Token', 'Role and minter', 'Status', 'Action']
  export const TOKEN_GRID: string;                 // '1.1fr 1.5fr .7fr 1fr' — the Users tab's own grid
  export function toTokenRows(items: TokenOut[], ui: TokensUi): Cell[][];
  export function tokenSubline(items: TokenOut[]): string;   // 'N live · last used <Month Year>' | 'N live · never used'
  export interface AdminTokensAdapter { list(): Promise<{ rows: Cell[][]; subline: string }>; }
  export function makeAdminTokensAdapter(ui?: TokensUi): AdminTokensAdapter;

  // frontend/src/admin/permissions.ts — additions
  export const PERMISSION_GRID: string;            // derived from ROLES.length, see below
  /** Composed from the PAYLOAD's own `reauth` / `token_denied` / `token_never_reauth`, so the two
   *  facts the matrix cannot show are read from the server rather than typed. There is ONE name:
   *  `toPermissionRows` returns `{ rows, legend }` and `permissionLegend(payload)` is what builds
   *  the string — no `PERMISSION_LEGEND` constant, because the sentence depends on the payload. */
  export function permissionLegend(payload: PermissionsPayload): string;
  ```
  **Task 19 reads `TOKEN_COLUMNS`, `TOKEN_GRID`, `toTokenRows`, `tokenSubline`, `AdminTokensAdapter`, `PERMISSION_GRID` and `permissionLegend`.** `PERMISSION_GRID` is `'1.4fr 1.8fr ' + ROLES.map(() => '.5fr').join(' ')` — **derived from `ROLES`, never typed**, so a seventh role gets a column without anyone remembering (the module's own existing rule for `PERMISSION_COLUMNS`).

- [ ] **Step 1: Write the failing tests**

```ts
// tokens.test.ts
it('shows a live token, a revoked one and an expired one with the design’s own three tones', () => { … });
it('offers Revoke only on a live token — revoking a revoked one changes nothing', () => { … });
it('routes Revoke through the step-up, because tokens.manage is in REAUTH', () => { … });
it('never prints a token secret, because the payload has none', () => { … });
it('composes the Settings sub-line from the live count and the newest last_used_at', () => {
  expect(tokenSubline(THREE)).toBe('1 live · last used September 2026');
  expect(tokenSubline(NEVER_USED)).toBe('1 live · never used');
  expect(tokenSubline([])).toBe('no tokens');
});

// permissions.test.ts
it('derives one column per role from ROLES, so a seventh role needs no edit here', () => {
  expect(PERMISSION_GRID.split(' ')).toHaveLength(2 + ROLES.length);
});
it('states D-C54 and the step-up list in the legend, from the payload and not from a literal', () => {
  expect(permissionLegend(PAYLOAD)).toContain('admin holds every permission');
  expect(toPermissionRows(PAYLOAD).legend).toContain('engine.activate');
});
it('says that an api token can never re-authenticate, which the matrix cannot show', () => {
  expect(toPermissionRows(PAYLOAD).legend).toContain('no api token can satisfy a step-up');
});
```

- [ ] **Step 2: Run them to verify they fail.**

- [ ] **Step 3: Write both modules.** `admin/permissions.ts`'s `toPermissionRows` changes its RETURN from `Cell[][]` to `{ rows: Cell[][]; legend: string }` — a breaking change to a module nothing imports yet (`grep -rn "admin/permissions" frontend/src --include=*.ts | grep -v permissions.test` returns only its own test), so update that test in the same commit and say so in the hand-back. It also gains the grid and a `reauth`/`token_denied` marker on the rows those name — the two facts the matrix alone cannot show, which the endpoint publishes beside it for exactly this reason.

- [ ] **Step 4: Declare the prop** — `adminTokens: { type: Object, default: () => makeAdminTokensAdapter(tokensUi()) }`.

- [ ] **Step 5: Gate and commit**

```bash
cd frontend && npm run typecheck && npm run build && npm test
git add frontend/src/admin/tokens.ts frontend/src/admin/tokens.test.ts \
        frontend/src/admin/permissions.ts frontend/src/admin/permissions.test.ts frontend/src/app.setup.js
git commit -m "feat(admin): the token list, and the matrix view's layout

admin/permissions.ts has mapped the matrix into cells since Task I7 and
computed no grid, because the design had no Permissions tab. It has one now,
and the grid is derived from ROLES so a seventh role needs no edit here.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 19: Settings rows 4 and 5, and the matrix view — A46.1–A46.7 (design)

Two more Settings rows — **API tokens** (Manage) and **Permissions** (View) — each opening a read-only table in the SAME drill-down panel A44.3 composed (decision D7 again: one panel, two more kinds).

**Re-basing states: ZERO re-based, TWO appended** (`admin-tokens`, `admin-permissions`, app only). **The thirteen frozen hashes must not move.**

**Files:** `frontend/tests/design-amendments.ts` + `.test.ts`, `frontend/src/admin/settings.ts` + `.test.ts` (the `tokenSubline` parameter Task 2 deferred), `frontend/src/logic.test.ts`, `frontend/tests/harness.ts` + `.test.ts`, `frontend/tests/design-admin-tokens.mjs`, `frontend/tests/smoke.spec.ts`, `LOCAL_AMENDMENTS.md`, `CLAUDE.md`.

**Interfaces:**
- Consumes: Task 18's `TOKEN_COLUMNS`, `TOKEN_GRID`, `toTokenRows`, `tokenSubline`, `AdminTokensAdapter`, `PERMISSION_GRID`, `PERMISSION_LEGEND`; Task 15's `openDetailPanel(kind, id)` — extended here to take `kind: 'tokens' | 'permissions'` with a `null` id, which is a widening of an existing parameter and adds no state key.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Add the `tokenSubline` parameter to `toSettingsRows`, RED first**

```ts
it('shows no token count until Manage has been opened — a screen must not demand a password to paint', () => {
  expect(toSettingsRows(PAYLOAD, ui(), activate, sendMail)[3][1].sub).toBe('—');
});
it('shows the served count once Manage has answered', () => {
  expect(toSettingsRows(PAYLOAD, ui(), '1 live · last used September 2026')[3][1].sub)
    .toBe('1 live · last used September 2026');
});
it('always offers Manage, and Permissions with no step-up at all', () => {
  const rows = toSettingsRows(PAYLOAD, ui(), activate, sendMail);
  expect(rows[3][3].actions.map((a) => a.label)).toEqual(['Manage']);
  expect(rows[4][0].main).toBe('Permissions');
  expect(rows[4][3].actions.map((a) => a.label)).toEqual(['View']);
});
```
Then add the parameter and the two rows. **`Permissions` takes no step-up**: `permissions.read` is staff-held and is not in `REAUTH` — asking for a password to read a policy table would be theatre.

- [ ] **Step 2: Write the failing structural test and the seven entries**

**The matrix is READ-ONLY and says so.** Spec §7: *"Grants are edited on the user's Access tab (§6), not here — the matrix is policy, grants are people."* So the matrix panel draws **no button of any kind**, and `frontend/src/logic.test.ts` asserts it: `expect(panel.rows.every((r) => r.every((c) => !c.hasActions))).toBe(true)`. Policy lives in `app/auth/permissions.py` under test, and editing it live would make the generated frontend twin stale.

**A46.1** `sets.settings.rows` reads the loaded rows (already Task 3's, so this entry is only the token sub-line plumbing), **A46.2** the panel's two new kinds in `openDetailPanel`, **A46.3** the panel's own table body for a `kind` with columns and a grid (the admin table's own `headStyle`/`rows` markup, reused inside the panel), **A46.4** the legend line beneath the matrix (the Data Sources footnote's own declarations), **A46.5** `loadAdmin` unchanged — tokens and permissions load on OPEN, not on arrival, because both cost a password or a matrix read nobody asked for, **A46.6** the step-up around `Manage`, **A46.7** clearing the panel on `go()`/`signOut` (A19.12's own shape, extended).

- [ ] **Step 3: Give the token panel its oracle**

`frontend/tests/design-admin-tokens.mjs` is a fixed `TokenOut[]` — one live, one revoked, one expired — that `harness.ts` answers `GET /api/admin/tokens` with, so the two `smoke.spec.ts` states are deterministic; `harness.test.ts` pins the stub the way A36's `/api/admin/users` stub is pinned.

- [ ] **Step 4: Run the closing sequence, C1 to C7.** Seven ledger rows, A46.1-A46.7. **C6's expected MOVED list is EMPTY** and its APPENDED list is empty (both new states are `smoke.spec.ts` cases). The hand-back also says whether `test_audited_permissions_are_written_by_their_handlers` needed the Task 17 Step 3 exemption.

---

## Task 20: `admin/listing_detail.ts` (A45)

`GET /api/admin/listings/{listing_id}` has been complete since Task SL8 and is reachable by nothing.

**Re-basing states: NONE.** **The thirteen frozen hashes must not move.**

**Files:** create `frontend/src/admin/listing_detail.ts` + `.test.ts`; modify `frontend/src/app.setup.js`.

**Interfaces:**
- Consumes: `GET /api/admin/listings/{id}` (read it: `sed -n '300,311p' app/api/admin_listings.py`); `GET /api/admin/audit`; Task 14's `DetailPanel` type, **imported, not re-declared**; `admin/listings.ts`'s `PILLS`/`ACTIONS`.
- Produces:
  ```ts
  export const LISTING_DETAIL_TABS: readonly string[];   // ['Overview', 'History']
  export function toListingDetail(detail: AdminListingDetail, auditRows: AuditRow[], tab: string, ui: DetailUi): DetailPanel;
  export interface AdminListingDetailAdapter { open(listingId: string): Promise<AdminListingDetail>; audit(listingId: string): Promise<AuditRow[]> }
  export function makeAdminListingDetailAdapter(ui?: DetailUi): AdminListingDetailAdapter;
  ```

- [ ] **Step 1: Write the failing tests** — the Overview facts (asking price, revenue, doctors, sq ft, ownership, market, status, seller); History's status changes **with the actor's NAME and date** and the decline reason; and the one thing this must NOT invent:

```ts
it('does not claim a photograph privacy state, because P9 has not landed', () => {
  expect(JSON.stringify(toListingDetail(DETAIL, [], 'Overview', ui()))).not.toMatch(/privacy|identifiab/i);
});
```
Spec §6 names "photographs' privacy state once P9 lands"; P9 has not landed (`feat/image-identifiability` is in flight), so the panel says nothing about it. **Record that in the module docstring as the deferred field, so the next implementer finds the seam rather than inventing one.**

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/admin/listing_detail.test.ts`
Expected: FAIL — `Failed to resolve import "./listing_detail"`.

- [ ] **Step 3: Write the module**

It imports `DetailPanel`, `DetailUi` and `AuditRow` from `./user_detail` — **it does not re-declare any of the three.** `LISTING_DETAIL_TABS` is `['Overview', 'History']`, two rather than three: a listing has no Access tab, because a listing holds no role grants. The Overview facts come from `GET /api/admin/listings/{id}`'s own payload and the History rows from the audit trail filtered on this `target_id`, with the same client-side-filter cost Task 14 Step 3 records — **name it in this module's docstring too**, because a reader of one module must not have to read the other to learn it.

The module docstring also names the DEFERRED field: photographs' privacy state (spec §6, "once P9 lands"). `feat/image-identifiability` is in flight and has not merged, so nothing here claims a privacy state, and the Step 1 test proves it.

- [ ] **Step 4: Declare the prop**

`frontend/src/app.setup.js`, beside `adminUserDetail`:
```js
  adminListingDetail: { type: Object, default: () => makeAdminListingDetailAdapter(detailUi()) },
```
`detailUi()` is the helper Task 14 Step 4 added; it is reused, not copied.

- [ ] **Step 5: Gate and commit**

```bash
cd frontend && npm run typecheck && npm run build && npm test
git add frontend/src/admin/listing_detail.ts frontend/src/admin/listing_detail.test.ts frontend/src/app.setup.js
git commit -m "feat(admin): the listing drill-down's adapter

GET /api/admin/listings/{id} has been complete since Task SL8 and reachable
by nothing. It says nothing about photograph privacy: P9 has not landed.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 21: The listing drill-down — A45.1–A45.4, and the ledger (A45)

**Re-basing states: ZERO re-based, ONE appended** (`admin-listing-detail`, app only). **`admin-listings` must not move** — the row click is A44.5's treatment exactly, and the same warning applies.

**Files:** `frontend/tests/design-amendments.ts` + `.test.ts`, `frontend/src/logic.test.ts`, `frontend/tests/smoke.spec.ts`, `LOCAL_AMENDMENTS.md`, `CLAUDE.md`.

**Interfaces:** consumes Task 20's `LISTING_DETAIL_TABS`, `toListingDetail`, `AdminListingDetailAdapter`, and Task 15's `openDetailPanel`/`detailPanel`/`admin.panel` — **four entries only, because the panel already exists**: **A45.1** the Listings row click, **A45.2** `openDetailPanel`'s `listing` branch routing to the other adapter, **A45.3** the kicker string (`"LISTING DETAIL"`), **A45.4** the `loadAdmin`-independent open (a detail is fetched on click, never on arrival).

- [ ] **Step 1: Write the failing real-browser case**

```ts
test('an admin Listings row opens the listing detail, with its history and its decline reason', async ({ page }) => {
  await reach(page, { screen: 'admin', persona: 'design' });
  await click(page, 'Listings');
  await page.getByText('Mixed practice — Bastrop').first().click();
  await expect(page.getByText('LISTING DETAIL')).toBeVisible();
  await click(page, 'History');
  await expect(page.getByText(/by .+ on /)).toBeVisible();
  await page.getByRole('button', { name: 'Close panel' }).click();
  await expect(page.getByText('LISTING DETAIL')).toHaveCount(0);
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npm run test:e2e -- -g 'opens the listing detail'`
Expected: FAIL — `LISTING DETAIL` never appears, because the Listings row carries no `open`.

- [ ] **Step 3: Print and count the four anchors, then write the four entries**

Anchors: A17.1's own Listings `rows:` ternary (A45.1, `Consumes A17.1`), Task 15's `openDetailPanel` body (A45.2, `Consumes A44.2`), Task 15's `admin.panel` render value (A45.3, `Consumes A44.4`) and Task 15's own markup kicker (A45.4, `Consumes A44.3`). Count each as a fixed string with the Task 3 Step 1 command before writing.

- **A45.1** — `admin/listings.ts`'s `toListingRows` gains an `open` on the first cell and the design's row mapping passes it through, exactly as A44.5 did for Users. **Same warning as A44.5: `cursor: pointer` goes on the ROW's existing style string; no underline, no colour change, no new element.**
- **A45.2** — `openDetailPanel`'s `kind === "listing"` branch calls `this.props.adminListingDetail.open(id)` instead of `adminUserDetail`, with the same rejection arm.
- **A45.3** — `admin.panel.kicker` reads `"LISTING DETAIL"` for that kind and `"USER DETAIL"` for the other; the tab list is `LISTING_DETAIL_TABS` (two) rather than `DETAIL_TABS` (three).
- **A45.4** — nothing new in the markup: the panel A44.3 wrote already renders `{{ admin.panel.kicker }}`, `{{ admin.panel.tabs }}` and `{{ admin.panel.rows }}`. **Confirm this by reading it, and if the markup DOES need an edit, that is a defect in A44.3's generality — say so rather than adding a second panel.**

- [ ] **Step 4: Regenerate, characterise, measure**

`frontend/src/logic.test.ts`, `describe('A45 — the listing drill-down')`: a Listings row click opens the panel with the listing kicker and calls the listing adapter, never the user one; a rejected `open` sets `detailErr` and leaves the panel closed; switching tabs re-fetches nothing; closing clears `detailData`.

- [ ] **Step 5: Run the closing sequence, C1 to C7.** Four ledger rows, A45.1-A45.4. **C6's expected MOVED list is EMPTY** — `admin-listings` in particular — and its APPENDED list is empty (`admin-listing-detail` is a `smoke.spec.ts` case).

---

## Task 22: `auth/seller_apply.ts` (A47)

`POST /api/applications` with `kind: "seller"` has existed since Wave 2a and **no screen calls it**, so `seller.apply` — a real permission held by buyers — is a door onto nothing.

**Re-basing states: NONE.** **The thirteen frozen hashes must not move.**

**Files:** create `frontend/src/auth/seller_apply.ts` + `.test.ts`; modify `frontend/src/app.setup.js`.

**Interfaces:**
- Consumes: `frontend/src/auth/api.ts`'s `apply(kind, fields)`; `app/api/applications.SELLER_REQUIRED = ("practice_name", "license_state")` and `ATTESTATION["seller"] = "ownership_attestation"`.
- Produces:
  ```ts
  export const SELLER_FIELDS: ReadonlyArray<{ key: string; label: string; hint: string; required: boolean }>;
  export interface SellerApplyAdapter { submit(fields: Record<string, unknown>): Promise<void> }
  export function makeSellerApplyAdapter(): SellerApplyAdapter;
  ```
  `SELLER_FIELDS` is `practice_name` (required), `license_state` (required — **decision D8**: the route validates it and the spec's four fields omit it), `city`, `zip`, `timing`, plus the `ownership_attestation` checkbox, which the design's access-request card already has as `affirm`.

- [ ] **Step 1: Write the failing tests**

```ts
it('asks for every field the route requires, and no field it discards', async () => {
  const required = SELLER_FIELDS.filter((f) => f.required).map((f) => f.key);
  expect(required).toEqual(['practice_name', 'license_state', 'ownership_attestation']);
});
it('POSTs kind "seller" with the fields as typed', async () => { … });
it('surfaces the route’s own refusal — a buyer who already has an open application', async () => {
  await expect(submitWith409()).rejects.toThrow('You already have an application under review.');
});
```

**Pin the field list across the language boundary**, the A22 mechanism: `tests/api/test_applications.py::test_the_design_seller_fields_equal_seller_required` reads `frontend/src/auth/seller_apply.ts`'s `SELLER_FIELDS` keys out of the file with a regex (no TypeScript parsing, the `step-fields.json` precedent — **or, better, move the list to `frontend/src/auth/seller-fields.json` and have both sides read the JSON**, which is what `frontend/src/listings/step-fields.json` already does and is the shape to copy).

- [ ] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/auth/seller_apply.test.ts` → FAIL, `Failed to resolve import "./seller_apply"`.
Run: `poetry run pytest tests/api/test_applications.py -k seller_fields` → FAIL, the file `frontend/src/auth/seller-fields.json` does not exist.

- [ ] **Step 3: Write `frontend/src/auth/seller-fields.json` and the module**

The JSON is the ONE list both sides read — `frontend/src/listings/step-fields.json`'s own precedent, so the pytest pin parses no TypeScript:

```json
[
  { "key": "practice_name", "label": "Practice name", "hint": "Hill Country Animal Hospital", "required": true },
  { "key": "license_state", "label": "License state", "hint": "TX", "required": true },
  { "key": "city", "label": "City or community", "hint": "Cedar Park", "required": false },
  { "key": "zip", "label": "ZIP code", "hint": "78613", "required": false },
  { "key": "timing", "label": "When you expect to sell", "hint": "Within 18 months", "required": false },
  { "key": "ownership_attestation", "label": "I own or co-own this practice", "hint": "", "required": true }
]
```

`seller_apply.ts` imports it, exports it as `SELLER_FIELDS`, and `submit(fields)` calls `apply('seller', fields)` and re-throws the route's own message.

- [ ] **Step 4: Declare the prop**

```js
  sellerApply: { type: Object, default: () => makeSellerApplyAdapter() },
```

- [ ] **Step 5: Both gates, then commit**

```bash
poetry run pytest tests/api/test_applications.py -q
cd frontend && npm run typecheck && npm run build && npm test
git add frontend/src/auth/seller_apply.ts frontend/src/auth/seller_apply.test.ts \
        frontend/src/auth/seller-fields.json frontend/src/app.setup.js tests/api/test_applications.py
git commit -m "feat(seller): the seller application adapter, and the field list both sides read

license_state is in the list because app.api.applications.SELLER_REQUIRED
validates it (decision D8); a form that omits a field the route requires
cannot complete.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 23: The seller-application card — A47.1–A47.6, and the ledger (A47)

Composed from the access-request card A8 built its nine gate screens on, with the seller intent fields (spec §8), reached from **"List a Practice"** for a buyer.

**Re-basing states: ZERO re-based, ONE appended** (`gate-seller-apply`, which **CAN** be a real `screens.ts` state, unlike every other state in this plan: the card is a GATE screen driven by the `startGate` prototype prop, which the reference already receives through `?props=` — A8's own mechanism. `startGate`'s enum widens by one value, exactly as A8.8b widened it to thirteen). **The thirteen frozen hashes must not move.**

**Files:** `frontend/tests/design-amendments.ts` + `.test.ts`, `frontend/src/logic.test.ts`, `frontend/tests/screens.ts`, `frontend/tests/harness.ts`, `frontend/src/router/sync.ts` (the new gate value's route), `LOCAL_AMENDMENTS.md`, `CLAUDE.md`.

**Interfaces:** consumes Task 22's `SELLER_FIELDS` / `seller-fields.json` and `SellerApplyAdapter`; produces the fourteenth `startGate` value, `seller-apply`.

- [ ] **Step 1: Extract the access-request card** — `python3 -c "…s.find('gate === \"apply\"')…"` and read the whole card, its fields, its affirmation checkbox, its primary button and its footer. **Every declaration in A47.3's markup is pasted from it.**

- [ ] **Step 2: Write the failing structural test**

```ts
describe('A47 — the seller application', () => {
  const amended = readFileSync(AMENDED, 'utf8');
  it('widens startGate by exactly one value', () => {
    expect(amended).toContain('"seller-apply"');
    expect((amended.match(/"enum":\s*\[[^\]]*"seller-apply"/g) ?? [])).toHaveLength(1);
  });
  it('asks for the two fields the route requires and the attestation', () => {
    for (const key of ['practice_name', 'license_state', 'ownership_attestation'])
      expect(amended).toContain(key);
  });
  it('is reached from "List a Practice" by an account that may apply but may not sell', () => {
    expect(amended).toContain('perms.allowed("seller.apply") && !perms.allowed("page.seller")');
  });
});
```

- [ ] **Step 3: Run it RED. Step 4: Write the six entries** — **A47.1** the `startGate` enum entry in the escaped `data-props` JSON (`Consumes A8.8b`), **A47.2** the gate state's own branch, **A47.3** the card's markup, **A47.4** the form state and its setters, **A47.5** the submit through the adapter with the card's own error slot, **A47.6** the "List a Practice" door routing a `seller.apply` holder here instead of onto the router's refusal.

**A47.6 is the entry that makes the door honest** and is the reason ruling 10.2 put A47 before the hidden doors: after this, "List a Practice" opens onto applying rather than onto a refusal, which is exactly what the A40 note recorded as the reason the item was "a door onto the refusal rather than a door onto applying".

- [ ] **Step 5: Append the approved state** — `frontend/tests/screens.ts` gains `gate-seller-apply`, reached on BOTH targets: `reach(p, { gate: 'seller-apply' })` on the reference through `?props=`, and on the app by signing in as the BUYER persona and clicking "List a Practice". Check `harness.ts`'s `reach` handles a gate value with an app-side click; if it does not, add it there rather than in `screens.ts`.

- [ ] **Step 6: Run the closing sequence, C1 to C7.** Six ledger rows, A47.1-A47.6, with `Consumes A8.8b` on A47.1's. **C6's expected APPENDED list is exactly one entry, `gate-seller-apply`, and its MOVED list is EMPTY** — a new gate value renders nothing on any existing screen. The commit message is:

```
feat(design): A47.1-A47.6 — a buyer can apply to sell

seller.apply has been a real permission with a real route and no screen
since Wave 2a, so "List a Practice" was a door onto a refusal. It is a door
onto applying now, composed from the access-request card A8 built its nine
gate screens on.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
```

---

## Task 24: The ninth prototype prop and the nav filter — A40.1/A40.2 (doors)

**Ruled 10.1: YES, and LAST.** A buyer sees "VIN Foundation Admin" and "List a Practice" and is refused by the router. A door that refuses is a fake affordance under D-C53.

**A40.1 and A40.2 have been RESERVED AND UNWRITTEN since 0.1.23 and their ids may not be reused. This task writes them.**

**Re-basing states: TWENTY-EIGHT, and SEVEN frozen hashes, all named in Task 25.** This task writes the code and MEASURES the movement; **Task 25 is where the re-pin is recorded.** Do not re-pin here.

**Files:** `frontend/tests/design-amendments.ts` + `.test.ts`, `frontend/src/logic.test.ts`, `frontend/tests/reference-server.mjs`, `frontend/tests/harness.ts`, `tests/auth/test_permissions.py`, regenerated bundle files.

**Interfaces:**
- Consumes: `frontend/src/auth/perms.ts`'s `PermsAdapter.allowed(perm)`.
- Produces: the ninth declared prototype prop `startRoles` (`string[] | null`, default `null`, section "Prototype", label "Signed-in account roles") and the design's `PROTOTYPE_NAV_ROLES` table.

- [ ] **Step 1: Write the failing cross-language pin FIRST**

Decision D9's whole safety rests on this, so it is written before the design edit:

```python
# tests/auth/test_permissions.py
def test_the_design_s_prototype_nav_table_equals_the_matrix():
    """A40.1/A40.2 (decision D9). The reference receives no `perms` adapter — it is the raw bundle
    driven by `?props=` — so the design carries a TWO-ROW fixture mapping the two nav permissions
    to their holders, used only when `this.props.perms` is absent. It is a fixture, not a second
    copy of the matrix, precisely because this test fails the day it disagrees with `MATRIX`."""
    design = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html").read_text(encoding="utf-8")
    m = re.search(r"const PROTOTYPE_NAV_ROLES = (\{.*?\});", design, re.S)
    assert m, "the design no longer carries the prototype nav table"
    table = json.loads(m.group(1).replace("'", '"'))
    assert set(table) == {"page.admin", "page.seller"}
    for perm, roles in table.items():
        assert sorted(roles) == sorted(PM.MATRIX[perm]), perm
```

- [ ] **Step 2: Run it to verify it fails** — `AssertionError: the design no longer carries the prototype nav table`.

- [ ] **Step 3: Write the two entries plus the prop**

- **A40.1** — the header nav array's two rows gain `perm: "page.admin"` and `perm: "page.seller"`, the array is filtered through one helper, and `PROTOTYPE_NAV_ROLES` is declared beside it. The helper, in full:
  ```js
  navAllowed(perm) {
    if (!perm) return true;
    if (this.props.perms) return this.props.perms.allowed(perm);
    // The reference receives no adapter and is driven by `?props=` alone, so it answers from the
    // prototype's own roles. `PROTOTYPE_NAV_ROLES` is pinned against `app.auth.permissions.MATRIX`
    // by `tests/auth/test_permissions.py::test_the_design_s_prototype_nav_table_equals_the_matrix`,
    // which is what makes it a fixture rather than a second copy of the matrix.
    var roles = this.props.startRoles;
    if (!roles) return true;
    return PROTOTYPE_NAV_ROLES[perm].some(function (r) { return roles.indexOf(r) > -1; });
  }
  ```
- **A40.2** — the `startRoles` entry in the escaped `data-props` JSON, spliced after `startMyListings` (`Consumes A16.11a`).

- [ ] **Step 4: Teach the oracle to hand it over**

`frontend/tests/reference-server.mjs` already injects `?props=` per request. `frontend/tests/harness.ts`'s `reach()` must, for the REFERENCE target, pass `startRoles` equal to the roles of the persona `SCREEN_PERSONA` picks for that screen — buyer for browse/detail/requests, seller for the wizard and dashboard, the all-roles design persona for admin. That is the whole fix: the oracle is then told what the app knows, which is the thing A40's note says was missing.

- [ ] **Step 5: Regenerate and MEASURE — do not re-pin**

```bash
cd frontend && npm run gen:design && npm run gen:logic && npm run gen:app
npm run typecheck && npm run build && npm test
npm run test:visual:baselines && npm run test:e2e
```
then C6 of the closing sequence, with its output KEPT — Task 25 reads this file:
```bash
node -e '
const {createHash}=require("crypto"),{readdirSync,readFileSync}=require("fs"),{join}=require("path");
const before=JSON.parse(readFileSync(process.env.PRE,"utf8")), d="tests/visual.spec.ts-snapshots";
for (const f of readdirSync(d).sort()) {
  const h=createHash("sha256").update(readFileSync(join(d,f))).digest("hex");
  if (!(f in before)) { console.log("APPENDED", f); continue; }
  if (before[f]!==h) console.log("MOVED", f);
}' PRE="$SCRATCH/doors-baselines-before.json" | sort > "$SCRATCH/doors-moved.txt"
cat "$SCRATCH/doors-moved.txt"
cp "$SCRATCH/doors-moved.txt" .superpowers/sdd/2026-09-11-neighbourhood-shading/doors-moved.txt
```
**Expected: exactly the states whose header loses a door for that screen's persona.** A40's own measurement was **28 of the 55 approved states** and **seven of the thirteen frozen hashes**. The count of approved states will differ — this plan has appended one (`gate-seller-apply`) and several families have re-based none — so **record what actually moved and compare it to the seven named in Task 25**. If a frozen row OUTSIDE those seven moved, stop with NEEDS_CONTEXT: the filter reached a screen it should not have.

- [ ] **Step 6: Commit the code, WITHOUT the manifest**

```bash
git add frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts frontend/src/logic.test.ts \
        frontend/tests/reference-server.mjs frontend/tests/harness.ts tests/auth/test_permissions.py \
        "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
        frontend/src/logic.js frontend/src/App.vue frontend/src/generated/pseudo.css
git commit -m "feat(design): A40.1/A40.2 — a door the account cannot open is not drawn

The ninth declared prototype prop, startRoles, is how the reference learns
what the app knows; the two-row nav table it answers from is pinned against
app.auth.permissions.MATRIX by pytest, so it cannot drift.

baseline-manifest.json is NOT touched in this commit: the ruled re-pin is
its own change (Task 25).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 25: The ruled re-pin of seven frozen captures (doors)

**This is the ONE task in this plan permitted to move a frozen hash, and it moves exactly seven, each named.** It is its own commit so a reviewer can reject the re-pin without rejecting the filter, and read the moved pixels on their own.

**The seven, from A40's own measurement (`detail`, `requests`, `seller-dash`, `wizard-step-1`, `wizard-step-7`, `wizard-preview`, `wizard-done`) — and the six that must NOT move (`mobile-list`, `mobile-detail`, `admin-users`, `admin-listings`, `admin-requests`, `admin-data-sources`).** The reasons, which the ledger row must carry:
- the seven are **desktop non-Browse screens captured as a persona that loses a door**: `detail`/`requests` as the BUYER (loses "VIN Foundation Admin" and, until A47.6, "List a Practice"); `seller-dash` and the four `wizard-*` as the SELLER (loses "VIN Foundation Admin");
- the four `admin-*` are captured as the **all-roles design persona**, which loses nothing;
- the two phone-frame captures render the prototype's own 390 × 800 header, not the site header — **which is the proof the change reached nothing else**, exactly as it was for A14.

**Files:** `frontend/tests/baseline-manifest.json`, `docs/design-reference/…/LOCAL_AMENDMENTS.md`, `CLAUDE.md`, `.superpowers/sdd/…/doors-moved.txt` (the measurement, kept).

- [ ] **Step 1: Confirm the measurement, one row at a time**

```bash
cd frontend
python3 - <<'PY'
import json, pathlib, hashlib
man = json.loads(pathlib.Path("tests/baseline-manifest.json").read_text())
snap = pathlib.Path("tests/visual.spec.ts-snapshots")
moved, held = [], []
for name in sorted(man["screens"]):
    f = next(snap.glob(f"{name}-*.png"), None) or next(snap.glob(f"{name}.png"), None)
    h = hashlib.sha256(f.read_bytes()).hexdigest()
    (moved if h != man["screens"][name] else held).append(name)
print("MOVED:", moved)
print("HELD :", held)
PY
```
**Expected MOVED, exactly:** `['detail', 'requests', 'seller-dash', 'wizard-done', 'wizard-preview', 'wizard-step-1', 'wizard-step-7']`.
**Expected HELD, exactly:** `['admin-data-sources', 'admin-listings', 'admin-requests', 'admin-users', 'mobile-detail', 'mobile-list']`.
**Anything else and you stop.** The glob line above assumes the snapshot filename pattern — check it against the directory before running (`ls tests/visual.spec.ts-snapshots | head`) and fix the glob, never the expectation.

- [ ] **Step 2: Look at the seven diffs**

```bash
npm run test:visual 2>&1 | tail -40      # after regeneration this passes; the point is the LAST pre-regeneration run
```
Open each of the seven new PNGs and confirm the ONLY change is the header's nav. Record one sentence per screen in the hand-back. **A screen whose change is anything else is a defect, not a re-pin.**

- [ ] **Step 3: Re-pin the seven, and only the seven**

```bash
python3 - <<'PY'
import json, pathlib, hashlib
p = pathlib.Path("tests/baseline-manifest.json"); man = json.loads(p.read_text())
snap = pathlib.Path("tests/visual.spec.ts-snapshots")
SEVEN = ["detail", "requests", "seller-dash", "wizard-done", "wizard-preview", "wizard-step-1", "wizard-step-7"]
for name in SEVEN:
    f = next(snap.glob(f"{name}-*.png"), None) or next(snap.glob(f"{name}.png"))
    man["screens"][name] = hashlib.sha256(f.read_bytes()).hexdigest()
p.write_text(json.dumps(man, indent=2) + "\n")
print("re-pinned", len(SEVEN))
PY
```

- [ ] **Step 4: Write the ledger rows and the CLAUDE.md paragraph**

The A40.1 and A40.2 rows in `LOCAL_AMENDMENTS.md` each carry the ruling verbatim (spec §10.1, controller, 2026-09-14), the `Consumes A16.11a` token on A40.2, and the seven re-pinned names IN THE ROW — the A14 and A6 precedent, where a ruled re-pin names what it re-pinned.

CLAUDE.md: the A40 paragraph's "**A40.1 and A40.2 are RESERVED AND UNWRITTEN**, and the ids may not be reused" sentence is now false and **must be replaced, not appended to** — write what they ARE, name the ninth prototype prop, name the seven re-pinned captures and the six that held, and re-take the counts sentence from the ledger. **Both byte-identical copies, written from one string.** `tests/test_docs.py` pins both.

- [ ] **Step 5: Merge main, every gate, and the final CI poll**

```bash
git merge --no-edit main
cd frontend && npm run gen:design && npm run gen:logic && npm run gen:app && npm run remap:citations
cd .. && poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m "not timing"
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m timing -p no:randomly --cov-append --cov-report=xml --cov-fail-under=100
cd frontend && npm run typecheck && npm run build && npm test && npm run test:visual:baselines && npm run test:e2e
```
Then re-run Step 1's script: **MOVED must now be empty.**

- [ ] **Step 6: Commit**

```bash
git add frontend/tests/baseline-manifest.json \
        docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md CLAUDE.md
git commit -m "chore(design): the ruled re-pin of seven frozen captures (A40.1/A40.2)

detail, requests, seller-dash and the four wizard captures lose a header
door their persona cannot open. The four admin captures and the two
phone-frame ones did not move, which is the proof the change reached
nothing else — the A14 mechanism.

Ruling: admin control surface spec §10.1 (controller, 2026-09-14), on the
recommendation the spec carried since 2026-09-13.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

Hand back: the MOVED/HELD lists from Steps 1 and 5, one sentence per re-based screen from Step 2, and a note that this is the reversible ruling — reverting Tasks 24 and 25 together restores the thirteen.

---
