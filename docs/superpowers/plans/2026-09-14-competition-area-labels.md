# Veterinary Competition — The Area, Named on Every Surface — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every surface that shows a veterinary-competition figure or its area says which area it is, in the D-C51 vocabulary — and the Browse map names its ~5-mile ring for the first time, with one legend row drawn exactly when the ring is drawn.

**Architecture:** Seven literal edits in one amendment family, **A48**, applied to the approved design through the D15 mechanism (`frontend/tests/design-amendments.ts` → `npm run gen:design` → `gen:logic` → `gen:app`), plus ONE new API constant. Nothing new is invented: the legend row is composed from the Market data card's own compare-key row and the design's own dashed-border treatment; the panel and strip captions are the card's own established scope lines; the two "said once" facts go on the "What this means" card (the dataset's own property) and on both footnotes byte for byte (the practice figure's own property). One approved state is appended so the ruled prose has an oracle — the D-C40 / A26-F2 gap.

**Tech Stack:** the design bundle's own dc runtime (React 18 + `support.js`) on the reference side · Vue 3 + `frontend/scripts/convert-dc.mjs` on the app side · Leaflet 1.9.4 behind `frontend/src/map/engine.ts` · Vitest 3 · Playwright (`reference-baselines.spec.ts`, `visual.spec.ts`, `dom.spec.ts`, `smoke.spec.ts`) · FastAPI · pytest.

**Branch:** one worktree, `.worktrees/feat-comp-labels`, cut from `main` at the time the work starts. Implementers never push, deploy or run `railway`; the controller does those at hand-back.

---

## The source of truth

`docs/superpowers/specs/2026-09-14-competition-area-labels-design.md`, whose §13 carries six decisions. **The controller has decided every one of them per the spec's own recommendation**, on 2026-09-14, and none is reopened here:

| # | Decision, as taken |
|---|---|
| 13.1 | **The dashed 26 × 9 outline in `--vf-navy`**, composed from the compare key's box and the design's own dashed-border treatment. Not a filled square. |
| 13.2 | **"About 5 miles around the selected practice"** — a key names a glyph; a caption names a figure. |
| 13.3 | **Two qualifiers, not one.** The strip card says `· estimated` (its `src` line already names the dataset); the panel sub-line says `· estimated from ZIP Code Business Patterns 2022` (the panel has no source line at all). |
| 13.4 | **The paid-employee universe on the "What this means" card only; the apportionment and the withheld-ZIP floor on BOTH footnotes, byte for byte.** |
| 13.5 | **`browse-market-strip` re-bases too** — four approved states move, plus one appended. Noted, not a question. |
| 13.6 | **The panel sub-line stays gated on a served `community_label`.** No widening to adapter presence. |

Above the spec sit John's rulings of 2026-09-14: **D-C55** (forward §1 of the brainstorm as the answer to the stakeholder), **D-C56** (D-C44 stands — no ring toggle, no chooser), **D-C57** (the map names the ring, with one legend row while a practice is selected, plus approach A's label fixes), **D-C58** (state premises registers are a research spike with no screen). The vocabulary they obey is **D-C51** (2026-09-13): every caption names **statistic · geography · basis**, and one fact is written once per surface that needs it.

### The amendment family id, and how it was derived

**A48**, per spec §8.1. It is derived from the ledger, not from this plan. Re-derive before writing a line:

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-comp-labels"
grep -c "id: 'A48" frontend/tests/design-amendments.ts        # expect 0
grep -c "^| A48" docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md   # expect 0
python3 - <<'PY'
import re, pathlib
md = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md").read_text(encoding="utf-8")
fams = sorted({int(re.match(r"A(\d+)", c).group(1))
               for line in md.split("\n") if line.startswith("| ")
               for c in [line.split("|")[1].strip()] if re.fullmatch(r"A\d+(\.\w+)*", c)})
print("families in the ledger:", fams)
PY
```

**A36–A39 are in flight on their own branches, A37 is reserved and unwritten, A40.1/A40.2 are reserved and unwritten (ids may not be reused), and A41–A47 are reserved by `docs/superpowers/specs/2026-09-13-admin-control-surface-design.md` §9.** A31.14 is a reserved sub-id inside an existing family and takes no family number. **If `grep -c "id: 'A48"` is not `0`, `main` has moved: STOP and re-derive — do not renumber on your own judgement.**

---

## Global Constraints

Every task's requirements implicitly include this section. Values are copied verbatim from the spec, the ledger, or the code they pin.

### From the spec's §2 — the rules this change obeys

- **(1) Reference open first, port verbatim, absent beats faked.** Every new element is an element V3 already carries, in the declarations V3 gives it, in the place V3's own idiom would put it. **No new state key, no new listener, and exactly ONE new render value** (`md.panel.compScope`, §5.1). The single place where two existing declarations are combined rather than one element copied is the ring swatch (§4) — decided at 13.1 and recorded as the family's one composition deviation.
- **(2) One fact, one string, per surface.** `metaSource`'s own rule (`frontend/src/logic.js:173-178`): a surface that already states a fact does not restate it, and a surface that states it nowhere gains it. This is why the panel's sub-line names the dataset and the strip card's does not — the strip card has a `src` line and the panel has none.
- **(3) Same fact, same words, on every surface that carries it.** A34.7/A34.8's rule: the two new competition sentences are **byte-identical** on the panel footnote and the strip footnote, "because the same three kinds of figure appear on both surfaces and two wordings of one fact is how they come to disagree."
- **(4) A ruled string gets an oracle.** One approved state is appended (Task 6).
- **(5) No new API field**, and no new route. One new module constant, `EMPLOYER_UNIVERSE`, appended to the EXISTING competition caveat (Task 1).
- **(6) The frozen thirteen do not move.** None of them is a Browse capture; every A48 entry edits the Browse screen's Market data card, docked panel or snapshot strip, or a `LAYER_META` string only those surfaces read. **Checked after the re-base, never assumed** (A18's discipline).

### The repo's standing rules

- **(a) `frontend/src/logic.js` is NEVER hand-edited, and neither is any bundle file.** Every change to the design is an entry in `frontend/tests/design-amendments.ts`, applied to the pristine copy by `npm run gen:design`, after which `npm run gen:logic` re-ports the script and `npm run gen:app` regenerates `App.vue`/`pseudo.css`; `frontend/tests/app-generated.test.ts` proves byte equality. `Practice Match V3.rev2.dc.html` and `MarketMapV3.rev2.jsx` are pristine and are never edited. **No A48 entry touches `MarketMapV3.jsx`** — the ring's own declarations do not change (D-C44/A28 stands; D-C56 confirms it), only the card that now names it.
- **(b) Every amendment's `find` is counted as a FIXED STRING before it is written, with Python and never `grep -c -F`** (`grep` splits on newlines and would OR a multi-line `find`):
  ```bash
  python3 -c "import pathlib,sys; print(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8').count(open(sys.argv[2],encoding='utf-8').read()))" <file> <anchor.txt>
  ```
  Every task below does this inline. `applyAmendments` throws if the count at the point of application is wrong; the point of the rule is to know BEFORE the run.
- **(c) 100 % coverage, both sides, warnings as errors.** Backend, exactly as CI runs it:
  ```bash
  docker compose -f docker-compose.dev.yml up -d
  poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m "not timing"
  poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m timing -p no:randomly --cov-append --cov-report=xml --cov-fail-under=100
  ```
  Frontend, **BUILD BEFORE TEST** (`vue-only.test.ts` and `bundle-budget.test.ts` read `frontend/dist/_app`):
  ```bash
  cd frontend && npm run typecheck && npm run build && npm test     # npm test is `vitest run --coverage`, the exact CI step
  ```
  `logic.js` is excluded from the measured set (it is the design's script) but every new branch in it is characterised in `frontend/src/logic.test.ts` regardless.
- **(d) Zero pixel tolerance, never relaxed.** `maxDiffPixels: 0` beside `threshold: 0.1` in `frontend/tests/playwright.config.ts` stays. Baselines regenerate from the amended design in the same run (`npm run test:visual:baselines`, the `reference` project), so a ruled change is legal there; a failure AFTER regeneration means the app and the design diverged — stop and diff, never widen the tolerance.
- **(e) No suppressions.** No `// eslint-disable`, no `# type: ignore`, no `test.skip`, no `it.skip`, no `xfail`, no `--cov-fail-under` below 100, no `pragma: no cover` added to make a gate green. A gate that cannot be made green as written is a NEEDS_CONTEXT.
- **(f) A guard must test the sentinel the producer actually emits.** Before writing any guard, run the real producer and print what it returns. The two this plan depends on, already measured at `ac1b34e`:
  - `marketVals(P).showDrive` is `!!(sel && Number.isFinite(sel.lat) && Number.isFinite(sel.lng))` — `false` for `mdSel: null`, `false` for a non-finite point, `true` only for a selected listing with a finite point. `Number.isFinite`, not `!= null`: a `NaN` passes `!= null`.
  - `locBasis` is `sel ? (sel.communityLabel || "community level") : ""` — an EMPTY STRING in AREA mode, not `undefined`, so `k === "competition"` must sit on the LOCATION arm of `valueNote`'s own ternary and nowhere else.
- **(g) `frontend/tests/baseline-manifest.json`'s THIRTEEN frozen hashes must not move.** `mobile-list`, `mobile-detail`, `detail`, `requests`, `seller-dash`, `wizard-step-1`, `wizard-step-7`, `wizard-preview`, `wizard-done`, `admin-users`, `admin-listings`, `admin-requests`, `admin-data-sources`. A moved hash means the change leaked outside Browse: stop with NEEDS_CONTEXT, **do not re-pin**.
- **(h) NO VERSION BUMP.** `frontend/package.json` and `pyproject.toml` stay at whatever `main` carries (0.1.24 at `ac1b34e`). The lockstep bump and the release are the controller's, after acceptance. `tests/test_versions.py` keeps the two in step either way.
- **(i) Playwright ports and databases never collide across worktrees, and there is NEVER a second compose stack.** The one dev stack is `docker compose -f docker-compose.dev.yml` on **5433** (Postgres) and **6380** (Redis) and it is shared; never start another on those ports or any other. This worktree exports, explicitly, in every shell that runs Playwright:
  ```bash
  export PW_APP_PORT=5593 PW_REF_PORT=5594 PW_CS_PORT=5595 PW_API_PORT=8167
  export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match_complabels
  export REDIS_URL=redis://localhost:6380/11
  for p in 5593 5594 5595 8167; do lsof -nP -iTCP:$p -sTCP:LISTEN && { echo "PORT $p BUSY — pick another and record it here"; exit 1; }; done
  ```
  Siblings hold `/0`, `/3`, `/7`, `/8`, `/9`, `/10` and ports 5473-5475/8047, 5503-5505/8347, 5513-5515/8357, 5573-5575/8147, 5583-5585/8157. **pytest and Playwright never share a database**: pytest clones per test from a template (`tests/conftest.py::scratch_dsn`) off `DATABASE_URL`, and `frontend/tests/targets.ts` runs `migrate.py` + `reset_rate_limits.py` + `seed_persona.py` + `seed_listings.py` against whatever `DATABASE_URL` names.
- **(j) A hand-maintained number in a comment or a document is a defect waiting to happen.** Where a figure can be derived from the tree, derive it. Counts in this plan are stated as **deltas** off a value measured when the task starts, never as absolutes typed at plan-cut time. The invariants are arithmetic and do not rot: `entries = literals + A1's derived count` · `ledger rows = literals + 1` · `baselines = screens.ts entries` · `families = distinct numbered ids in design-amendments.ts, PLUS ONE for A1`.
- **(k) Surgical diffs, no destructive actions, conventional commits with explicit pathspecs.** `git add <path> …`, never `git add -A`. Every commit ends with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Implementers never `git stash`, never touch another worktree, and never push.
- **(l) Merge `main` before the final push, and merge ledger branches one at a time.** `design-amendments.ts` and `LOCAL_AMENDMENTS.md` collide on every amendment branch; four are in flight (A36, A38, A39, plus whatever lands). Merge `main` into this branch before Task 7's push, re-run `npm run remap:citations`, and re-take every derived count after the merge.
- **(m) CI is polled in the FOREGROUND.** A subagent never receives a background-completion notification. Any wait on `gh run` is a bounded foreground loop (Task 7 gives the exact one).
- **(n) Deviations STOP.** A `find` that does not match with `count: 1` at its point of application, a frozen hash the plan did not predict, a fifth re-based state, a DOM-oracle line after regeneration, a coverage gate that needs relaxing — stop and report as NEEDS_CONTEXT. Do not improvise.

---

## Preconditions

Run these once, at the start of the branch, **before any design edit**. If any fails, STOP.

```bash
cd "/Users/johndean/Development/Practice Match"
git worktree add .worktrees/feat-comp-labels -b feat/comp-labels main
cd .worktrees/feat-comp-labels
git log --oneline -1                       # the base; record it in the hand-back

# The family id is free
grep -c "id: 'A48" frontend/tests/design-amendments.ts                 # 0
grep -c "^| A48" docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md   # 0

# The seven anchors all occur exactly once in the AMENDED design
python3 - <<'PY'
import pathlib
s = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html").read_text(encoding='utf-8')
p = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.rev2.dc.html").read_text(encoding='utf-8')
anchors = {
 "A48.1": '    means: "Establishment counts show how many veterinary businesses operate nearby. They say nothing about size, quality or overlap in services.",\n',
 "A48.2": '                    </sc-if>\n                    <div style="margin-top: 11px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.sourceLine }}</div>\n',
 "A48.3": '      overviewScope: sel.communityLabel || "",\n',
 "A48.4": '                  <div style="font-family: var(--rf-display); font-size: 14.5px; font-weight: 800; color: var(--vf-navy); margin-top: 18px;">Competitive Landscape</div>\n                  <sc-if value="{{ md.panel.hasOverviewScope }}" hint-placeholder-val="{{ false }}">\n                    <div style="font-size: 12.5px; color: var(--vf-text); margin-top: 2px;">{{ md.panel.overviewScope }}</div>\n',
 "A48.5": 'Affluence compares this practice’s median income with the US median; growth is the surrounding city or county’s; payroll is the county’s.</p>',
 "A48.6": 'Population growth is measured for the surrounding city or county, not the tract.</p>',
 "A48.7": '                : k === "income" ? (sel.incomeNote ? (sel.incomeNote.indexOf(" · ") > -1 ? sel.incomeNote : locBasis + " · " + sel.incomeNote) : locBasis) : locBasis)\n',
}
for k, v in anchors.items():
    print(k, "amended:", s.count(v), "pristine:", p.count(v))
PY
```

Expected, exactly:

```
A48.1 amended: 1 pristine: 1
A48.2 amended: 1 pristine: 0
A48.3 amended: 1 pristine: 0
A48.4 amended: 1 pristine: 0
A48.5 amended: 1 pristine: 0
A48.6 amended: 1 pristine: 0
A48.7 amended: 1 pristine: 0
```

**`pristine: 0` on six of the seven is expected and is the point:** those anchors are earlier entries' output, so each A48 entry must run AFTER the entry that produced its anchor. Appending the A48 block last in `amendments()` satisfies every one of them (A48.2 after **A24.8a**, A48.3 after **A27.6**, A48.4 after **A34.6**, A48.5 after **A34.7**, A48.6 after **A34.8**, A48.7 after **A34.16**). A48.1's anchor is pristine, so it is unchained.

**Then take the pre-change baseline hash map** — Task 6 measures the re-base set against it, the A33 way, rather than reasoning about it:

```bash
export PW_APP_PORT=5593 PW_REF_PORT=5594 PW_CS_PORT=5595 PW_API_PORT=8167
export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match_complabels
export REDIS_URL=redis://localhost:6380/11
docker compose -f docker-compose.dev.yml up -d
cd frontend && npm run test:visual:baselines
node -e '
const {createHash}=require("crypto"), {readdirSync,readFileSync,writeFileSync}=require("fs"), {join}=require("path");
const d="tests/visual.spec.ts-snapshots", out={};
for (const f of readdirSync(d).sort()) out[f]=createHash("sha256").update(readFileSync(join(d,f))).digest("hex");
writeFileSync(process.env.PRE+"", JSON.stringify(out,null,2)+"\n");
console.log(Object.keys(out).length+" baselines hashed");
' PRE=/private/tmp/claude-502/-Users-johndean-Development-Practice-Match/39b87aac-a222-47b1-8bec-a538c22fdc1f/scratchpad/a48-baselines-before.json
```

(`PRE` is passed through the environment so the path is not embedded in the script; use whatever scratchpad path this session carries and record it in the hand-back.) Expected: **one hash per `screens.ts` entry** — 55 at `ac1b34e`; derive it, never type it.

---

## File Map

| File | Kind | Responsibility | Task |
|---|---|---|---|
| `app/api/market.py` | modify | `EMPLOYER_UNIVERSE` beside `THRESHOLD_RULE`; appended to `LAYERS[competition]["caveat"]` | 1 |
| `docs/integrations/market-data-api.md` | modify | the `/api/layers` sample's competition `caveat`, made equal to what the router serves | 1 |
| `tests/api/test_contract_doc.py` | modify | the doc's competition caveat is the router's own string, byte for byte | 1 |
| `tests/census/test_design_shading_labels.py` | modify | `EMPLOYER_UNIVERSE` is one sentence read by both sides; `LAYER_META.competition.means` names the geography it shades | 1 (API half), 2 (design half) |
| `frontend/tests/design-amendments.ts` | modify | the seven A48 entries, in id order, appended as the last family block | 2, 3, 4, 5 |
| `frontend/tests/design-amendments.test.ts` | modify | the seven ids in `AMENDMENT_IDS`, the `toHaveLength` count, and the family's own structural case | 2, 3, 4, 5 |
| `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html` | **regenerated** | `npm run gen:design` | 2, 3, 4, 5 |
| `frontend/src/logic.js`, `frontend/src/App.vue`, `frontend/src/generated/pseudo.css`, `frontend/src/app.setup.js` | **re-ported / regenerated** | `npm run gen:logic`, `npm run gen:app` — never hand-edited | 2, 3, 4, 5 |
| `frontend/src/logic.test.ts` | modify | `describe('A48 — …')`, one characterisation per entry; and the ONE existing A34 case A48.7 moves | 2, 3, 4, 5 |
| `tests/census/test_band_distance.py` | modify | the fifth derivation of the one radius — the legend row's own sentence | 5 |
| `frontend/tests/smoke.spec.ts` | modify | the ring-row case; and the ONE existing A34 assertion A48.4 moves | 4, 5 |
| `frontend/tests/screens.ts` | modify | `browse-insight-competition` appended | 6 |
| `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md` | modify | one row per A48 entry, in apply order, with `V3:` citations and `Consumes` tokens | 7 |
| `CLAUDE.md` | modify | the A48 paragraph and the derived count sentences, in BOTH copies of the "Source of truth" block | 7 |

---

## Task 1: `EMPLOYER_UNIVERSE` — one sentence the API and the design will both read

The paid-employee universe is a property of the **dataset**, not of a listing and not of a polygon, so it is a module constant appended to the competition layer's EXISTING caveat rather than a new payload field (spec §7). This task lands the API half and its pins. **The design half is Task 2**, and the cross-wire pin ("the sentence is in the design exactly once") goes there with it — a task must not end red, and the design does not carry the sentence until A48.1 is applied.

**Re-basing states: NONE.** Nothing in the design changes. **The thirteen frozen hashes must not move** (nothing renders differently).

**Files:**
- Modify: `app/api/market.py:304-311` (`THRESHOLD_RULE`'s own block — `EMPLOYER_UNIVERSE` goes immediately beneath it) and `:321` (the competition layer's `caveat`)
- Modify: `docs/integrations/market-data-api.md:77-80` (the `/api/layers` sample's competition object)
- Test: `tests/census/test_design_shading_labels.py`, `tests/api/test_contract_doc.py`

**Interfaces:**
- Consumes: nothing from an earlier task.
- Produces, from `app/api/market.py`:
  ```python
  EMPLOYER_UNIVERSE: str = (
      "The Census counts business locations with paid employees, so a practice with "
      "no paid staff is not in this figure."
  )
  ```
  i.e. the exact string `"The Census counts business locations with paid employees, so a practice with no paid staff is not in this figure."` — **Task 2's A48.1 embeds this sentence verbatim** in `LAYER_META.competition.means`, and Task 2's pytest pin asserts it occurs in the amended design exactly once. `THRESHOLD_RULE` is unchanged and keeps its own place at the END of the caveat.

- [ ] **Step 1: Write the failing tests**

Append to `tests/census/test_design_shading_labels.py`, after `test_the_census_threshold_rule_is_one_sentence_read_by_both_the_api_and_the_design`. Extend the module's existing import line to carry the new constant:

```python
from app.api.market import BOUNDARY_METRIC, EMPLOYER_UNIVERSE, SHADING, THRESHOLD_RULE
```

and add:

```python
def test_the_paid_employee_universe_is_one_sentence_the_catalogue_serves() -> None:
    """D-C57 (John, 2026-09-14), spec §7: ZIP Code Business Patterns counts business locations
    WITH PAID EMPLOYEES, so a practice run by its owner alone is not in the figure at all. That
    was stated nowhere in the product. It is a property of the DATASET and constant for every
    listing in the country, so it is appended to the layer catalogue's existing `caveat` rather
    than served as a per-listing field -- which means an integrator reading `/api/layers` and a
    buyer reading the "What this means" card get ONE wording.

    Pinned here in `THRESHOLD_RULE`'s own shape. The DESIGN half of this pin -- the sentence
    occurs in the amended design exactly once -- lands with amendment A48.1, which is what puts
    it there; this case owns the server side alone."""
    competition = next(layer for layer in LAYERS if layer["key"] == "competition")
    caveat = competition["caveat"]
    assert EMPLOYER_UNIVERSE in caveat, (
        "the competition caveat no longer states the universe the Census actually counts"
    )
    assert caveat.count(EMPLOYER_UNIVERSE) == 1, "the universe is stated once in the caveat, not twice"
    # …and the rule it sits beside is untouched: two facts, two sentences, one caveat.
    assert THRESHOLD_RULE in caveat, "appending the universe dropped the Census threshold rule"
    assert EMPLOYER_UNIVERSE.endswith("."), "a caveat is composed by joining sentences with a space"
```

`LAYERS` joins the module's import line too:

```python
from app.api.market import BOUNDARY_METRIC, EMPLOYER_UNIVERSE, LAYERS, SHADING, THRESHOLD_RULE
```

And append to `tests/api/test_contract_doc.py`:

```python
def test_contract_doc_serves_the_competition_caveat_the_router_actually_sends() -> None:
    """Spec §7: `docs/integrations/market-data-api.md` gains the widened caveat.

    MEASURED before it was written (2026-09-14): the doc's `/api/layers` sample already carried a
    TRUNCATED competition caveat -- it stopped before `THRESHOLD_RULE`, which the router has
    appended since the ZIP-threshold work -- and nothing pinned it, so the document told an
    integrator one thing and the route sent another. The pin is therefore on the WHOLE string
    rather than on the new sentence alone: the sample is what the router serves, byte for byte,
    and a caveat that grows on one side fails here instead of drifting on the other."""
    from app.api.market import LAYERS

    doc = DOC.read_text(encoding="utf-8")
    caveat = next(layer for layer in LAYERS if layer["key"] == "competition")["caveat"]
    assert caveat is not None
    assert f'"caveat": "{caveat}"' in doc, (
        "the contract document's competition caveat is not the string the router sends:\n"
        f"  router: {caveat!r}"
    )
```

**Two house rules of that file, both obeyed above and neither optional.** `DOC` — not `ROOT` — is the module's own path constant (`tests/api/test_contract_doc.py:26`). And **`app.api.market` is imported INSIDE the test function, never at module scope**: that module's own docstring records the ruling (A-C0 ¶12 / A-C15 (7)) and says it is about how the file is written, not about whether the import happens to succeed today.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-comp-labels"
poetry run pytest tests/census/test_design_shading_labels.py::test_the_paid_employee_universe_is_one_sentence_the_catalogue_serves \
                  tests/api/test_contract_doc.py::test_contract_doc_serves_the_competition_caveat_the_router_actually_sends -q
```

Expected: **2 failed.** The first fails at collection with `ImportError: cannot import name 'EMPLOYER_UNIVERSE' from 'app.api.market'`. The second fails on the assertion, naming the router's string — the doc's sample stops at `"…that dataset's own authoritative geography."` and the router's string continues with `THRESHOLD_RULE`.

- [ ] **Step 3: Write the minimal implementation**

In `app/api/market.py`, immediately after the `THRESHOLD_RULE` assignment (its closing `)` at line 311 today) and before the `# The nine approved layers` comment, insert:

```python

# The UNIVERSE ZIP Code Business Patterns counts, stated once and read in two places: this
# catalogue's `competition` caveat, which an integrator reads, and -- word for word -- the design's
# "What this means" card, which a buyer reads (amendment A48.1, D-C57). ZBP counts business
# LOCATIONS WITH PAID EMPLOYEES, so a practice run by its owner alone is not in the figure at all;
# that was stated nowhere in the product until 2026-09-14. It is constant for every listing in the
# country, which is why it is a caveat sentence and not a served field (spec §7).
EMPLOYER_UNIVERSE = (
    "The Census counts business locations with paid employees, so a practice with "
    "no paid staff is not in this figure."
)
```

and change the competition layer's `caveat` (line 321) so the new sentence sits between the geography sentence and the threshold rule — the caveat then reads dataset scope, then geography, then universe, then the publication rule:

```python
    {"key": "competition", "label": "Veterinary Competition", "dataset_key": "zbp", "metric": "establishments", "is_derived": False, "geo_level": "zcta",
     "caveat": "Establishment counts (NAICS 541940) include corporate-owned and specialty locations; a proxy for competitive density, not a count of independent practices. Published per ZIP code by ZIP Code Business Patterns, and shaded at the ZIP Code Tabulation Area, which is that dataset's own authoritative geography. " + EMPLOYER_UNIVERSE + " " + THRESHOLD_RULE},
```

Then update `docs/integrations/market-data-api.md`'s competition object (line 80 today) so its `"caveat"` is that whole string. Print it rather than retyping it:

```bash
poetry run python -c "
from app.api.market import LAYERS
print(next(l for l in LAYERS if l['key']=='competition')['caveat'])
"
```

and paste the printed line into the sample as `"caveat": "<printed>" },`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
poetry run pytest tests/census/test_design_shading_labels.py tests/api/test_contract_doc.py -q
```

Expected: PASS, all of them — including `test_contract_doc_names_every_market_and_admin_route` and the existing threshold-rule case, neither of which this touches.

- [ ] **Step 5: Run the full backend gate**

```bash
docker compose -f docker-compose.dev.yml up -d
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m "not timing"
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m timing -p no:randomly --cov-append --cov-report=xml --cov-fail-under=100
poetry run ruff check .
poetry run mypy app --strict
```

Expected: green, 100 % coverage. A module-level constant adds no branch.

- [ ] **Step 6: Commit**

```bash
git add app/api/market.py docs/integrations/market-data-api.md tests/census/test_design_shading_labels.py tests/api/test_contract_doc.py
git commit -m "feat(market): state the paid-employee universe ZBP counts, once, in the layer caveat

D-C57 (John, 2026-09-14). ZIP Code Business Patterns counts business locations WITH
PAID EMPLOYEES, so a practice with no paid staff is not in the competition figure at
all — a fact stated nowhere in the product. It is constant for every listing in the
country, so it is appended to the existing competition caveat rather than served as a
field (spec §7), and the design will read the same sentence (A48.1).

Measured while pinning it: the contract document's sample caveat was already truncated
against the router's own string — it stopped before THRESHOLD_RULE — so the pin is on
the whole caveat and the sample is now what the route sends, byte for byte.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 2: A48.1, A48.5, A48.6 — the prose: the card names its area and its universe, both footnotes name the floor

Three literal edits and the family's first appearance in `design-amendments.ts`.

- **A48.1** replaces `LAYER_META.competition.means`. Today it names no area at all ("operate nearby"), which is D-C57's other label fix, and it says nothing about the universe. One string carries both corrections. The anchor is **pristine**, so nothing is consumed.
- **A48.5** and **A48.6** append the SAME two sentences to the docked panel's footnote and the snapshot strip's footnote. They go to both because the practice's competition figure appears on both surfaces and the "What this means" card is never guaranteed to be on screen beside it (it is dismissible, it needs competition to be the active layer, and it needs a map at least 810 px wide). **"Said once" means one wording, not one location** — A34.8's own recorded holding.
- Both footnote entries **APPEND** and rewrite nothing: every existing sentence is carried forward byte for byte, A24.20's growth caveat and A27.4's straight-line sentence included. That is the fix-round-3 lesson AMEND-GUARD exists for.

**Re-basing states, predicted:** A48.1 → **none of the current approved states** (the card renders the ACTIVE layer's prose and no state selects competition — Task 6 appends the state that photographs it). A48.5 → `browse-market-panel`, `browse-panel-lightbox`. A48.6 → `browse-market-strip`, `browse-market-strip-location`. **Measured in Task 6, not here.** **The thirteen frozen hashes must not move.**

**Files:**
- Modify: `frontend/tests/design-amendments.ts` (the A48 block, appended last in `amendments()`, with the three entries defined in id order above it)
- Modify: `frontend/tests/design-amendments.test.ts` (`AMENDMENT_IDS`, the `toHaveLength` count, and the family's structural case)
- Modify: `frontend/src/logic.test.ts` (the new `describe('A48 — …')`)
- Modify: `tests/census/test_design_shading_labels.py` (the design half of Task 1's pin, and the geography pin on `means`)
- Regenerated: the `.dc.html`, `logic.js`, `App.vue`, `pseudo.css`, `app.setup.js`

**Interfaces:**
- Consumes, from Task 1: `app.api.market.EMPLOYER_UNIVERSE` — the exact sentence `"The Census counts business locations with paid employees, so a practice with no paid staff is not in this figure."`, which A48.1 embeds verbatim.
- Produces, for Tasks 3–7:
  - `LAYER_META.competition.means` (readable in vitest as `c.marketVals(P).active.means` with `mdValue: 'competition'`) is exactly:
    `"Establishment counts show how many veterinary businesses operate in each ZIP Code Tabulation Area. The Census counts business locations with paid employees, so a practice with no paid staff is not in this figure. They say nothing about size, quality or overlap in services."`
  - The two appended sentences, **identical on both footnotes** (curly apostrophes, U+2019):
    `"A practice’s competition figure apportions each ZIP area’s published count to the part of that ZIP within about 5 miles of the practice. A ZIP whose count the Census withheld adds nothing to it, so the figure is a floor rather than an exact count."`
  - Amendment ids `A48.1`, `A48.5`, `A48.6` exist in `amendments()` and in `AMENDMENT_IDS`. Task 7 writes their ledger rows; **A48.5's row must carry `Consumes A34.7` and A48.6's must carry `Consumes A34.8`**, because each rewrites the whole `<p>` line that entry introduced.

- [ ] **Step 1: Write the failing tests**

(a) Append to `frontend/src/logic.test.ts`, at the end of the file, a new top-level `describe`:

```ts
// ---------------------------------------------------------------------------------------
// A48 — TASK COMP-LABELS (John's rulings D-C55–D-C58, 2026-09-14). The stakeholder asked what
// area the veterinary-competition number describes, and the product answered nowhere: the
// "What this means" card said "nearby", the map drew an unlabelled ring, and the selected
// practice's figure carried the ring caption with no word about how it is derived. D-C57: every
// surface that shows the figure or its area names it, in D-C51's vocabulary.
// ---------------------------------------------------------------------------------------
describe('A48 — the competition figure names its area, its universe and its floor (D-C57)', () => {
  const AUSTIN = 'Austin, TX';
  const ZIP = 'ZIP Code Tabulation Area';
  const UNIVERSE = 'The Census counts business locations with paid employees, so a practice with no paid staff is not in this figure.';

  const browse = (layer: string, sel: string | null) =>
    c.setState({ auth: true, screen: 'browse', market: AUSTIN, mdSel: sel, mdValue: layer });

  it('A48.1 — the "What this means" card names the area it shades and the universe it counts', () => {
    browse('competition', null);
    expect(c.marketVals(P).active.means).toBe(
      'Establishment counts show how many veterinary businesses operate in each ZIP Code Tabulation Area. '
      + UNIVERSE
      + ' They say nothing about size, quality or overlap in services.'
    );
  });

  it('…and it names ITS OWN geography and no other layer\'s (the copy-paste catch)', () => {
    browse('competition', null);
    const means: string = c.marketVals(P).active.means;
    expect(means, 'the competition card no longer names the ZIP area it shades').toContain(ZIP);
    for (const other of ['Census tract', 'Place (city/town)', 'County']) {
      expect(means, `the competition card names ${other}, which is not the geography it shades`).not.toContain(other);
    }
  });

  it('…and the other five layers\' prose is byte-identical to what it was', () => {
    // The ruling reached ONE layer's `means`. Pinned as literals, because the whole point of a
    // characterisation case is that a later edit to the shared `LAYER_META` object cannot move a
    // neighbour in silence.
    const UNCHANGED: Record<string, string> = {
      income: 'Higher-income areas may support stronger demand, but income alone does not indicate practice performance.',
      pets: 'This is a modelled estimate of how many households in an area keep pets, not a measured figure.',
      growth: "Growth describes how fast an area's population changed. Past growth is not a forecast.",
      households: 'The count of occupied housing units in each community — the denominator behind most other figures here.',
      econ: "A derived market-level indicator of how large the typical veterinary employer in an area is. It is not revenue, and not any individual practice's figures."
    };
    for (const [layer, text] of Object.entries(UNCHANGED)) {
      browse(layer, null);
      expect(c.marketVals(P).active.means, `${layer}'s prose moved and this ruling did not touch it`).toBe(text);
    }
  });
});
```

(b) Append to `frontend/tests/design-amendments.test.ts`, inside its top-level `describe`, the family's structural case — the footnote sentences are TEMPLATE literals, not `logic.js`, so they are asserted against the amended design file rather than in `logic.test.ts`:

```ts
  it('A48.5/A48.6 append the SAME two competition sentences to both footnotes, and rewrite neither', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    const APPORTION = 'A practice’s competition figure apportions each ZIP area’s published count to the part of that ZIP within about 5 miles of the practice.';
    const FLOOR = 'A ZIP whose count the Census withheld adds nothing to it, so the figure is a floor rather than an exact count.';
    // Rule 3 (spec §2): the same figure appears on both surfaces, so it is described in the same
    // words on both — two wordings of one fact is how they come to disagree (A34.7/A34.8).
    expect(amended.split(`${APPORTION} ${FLOOR}`).length - 1, 'the pair is on the panel footnote and the strip footnote, and nowhere else').toBe(2);
    // Every sentence that was there is still there, byte for byte — the fix-round-3 lesson.
    for (const carried of [
      'A catchment figure is a straight-line area of about 5 miles around the practice, not a driving route.',
      'Affluence compares this practice’s median income with the US median; growth is the surrounding city or county’s; payroll is the county’s.',
      'Population growth is measured for the surrounding city or county, not the tract.',
      'Pet-household counts and average practice payroll are derived estimates, not observed values.'
    ]) {
      expect(amended.split(carried).length - 1, `A48.5/A48.6 dropped a ruled sentence: ${carried}`).toBe(1);
    }
    // …and each pair is at the END of its own paragraph, not spliced into the middle of one.
    expect(amended.split(`${FLOOR}</p>`).length - 1, 'the sentences were not appended at the end of both paragraphs').toBe(2);
  });
```

(c) Append to `tests/census/test_design_shading_labels.py`, beneath Task 1's case:

```python
def test_the_paid_employee_universe_is_the_same_sentence_in_the_design() -> None:
    """The DESIGN half of the pin Task 1 opened. Amendment A48.1 puts the sentence on the "What
    this means" card, which is the one surface whose whole purpose is that layer's prose, and it
    is a SUBSTRING of that card's string -- so the design states the fact once and both sides read
    one wording. Same shape as `test_the_census_threshold_rule_is_one_sentence_read_by_both_the_api_and_the_design`."""
    design = DESIGN.read_text(encoding="utf-8")
    assert EMPLOYER_UNIVERSE in design, "the design's card no longer states the universe the API states"
    assert design.count(EMPLOYER_UNIVERSE) == 1, "the universe is stated once in the design, not twice"


def test_the_competition_prose_names_the_geography_that_layer_shades() -> None:
    """D-C57's other label fix, pinned the way `test_every_layer_row_names_the_geography_that_layer_shades`
    pins the drawer rows: the card's prose names `SHADING["competition"]["label"]` and no other
    layer's geography, so a layer that moves geography again fails on both sides at once.

    SCOPED TO COMPETITION DELIBERATELY. D-C57 reached one layer's `means`; the other five are
    unruled prose about what a figure is FOR (`households` says "in each community", `econ` says
    "market-level") and sweeping them here would assert a ruling nobody has made."""
    design = DESIGN.read_text(encoding="utf-8")
    start = design.index("const LAYER_META = {")
    block = design[start:design.index("\n};", start)]
    comp = block[block.index("  competition: {"):]
    m = re.search(r'    means: "([^"]*)",', comp)
    assert m, "the design no longer declares LAYER_META.competition.means"
    means = m.group(1)
    own = RULED_LABEL["competition"]
    assert own in means, f"the competition card does not name its own geography {own!r}: {means!r}"
    for label in RULED_LABEL.values():
        if label == own:
            continue
        assert label.lower() not in means.lower(), (
            f"the competition card names {label!r}, which is not the geography it shades"
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-comp-labels/frontend"
npx vitest run src/logic.test.ts -t "A48" ; npx vitest run tests/design-amendments.test.ts -t "A48.5/A48.6"
cd .. && poetry run pytest tests/census/test_design_shading_labels.py -q -k "paid_employee_universe_is_the_same_sentence or competition_prose_names"
```

Expected:
- vitest `A48.1 — the "What this means" card…` FAILS on the string: `expected 'Establishment counts show how many veterinary businesses operate nearby. They say nothing about size, quality or overlap in services.' to be 'Establishment counts show how many veterinary businesses operate in each ZIP Code Tabulation Area. …'`
- vitest `…and it names ITS OWN geography` FAILS: `the competition card no longer names the ZIP area it shades`
- vitest `…and the other five layers' prose` PASSES already (it is a characterisation of what is there)
- vitest `A48.5/A48.6 append…` FAILS: `the pair is on the panel footnote and the strip footnote, and nowhere else: expected 0 to be 2`
- pytest: **2 failed** — `the design's card no longer states the universe the API states`, and `the competition card does not name its own geography 'ZIP Code Tabulation Area'`

- [ ] **Step 3: Write the three amendment entries**

In `frontend/tests/design-amendments.ts`, at the END of the file's entry definitions (after `A34_23`, before `amendments()`), add the family's header comment and the three entries. Keep definition order equal to list order (the m8 convention), inserting later tasks' entries at their own id position inside this block.

```ts
/** ------------------------------------------------------------------------------------------
 *  A48 — TASK COMP-LABELS (John's rulings D-C55–D-C58, 2026-09-14). The stakeholder's question,
 *  verbatim: "Under the demographic metrics, one of the options is veterinary competition, and it
 *  looks like it's the number of practices in a given area, but the area is not defined."
 *
 *  D-C56 confirms D-C44 — no ring toggle and no 5/10-mile chooser — and D-C57 rules that every
 *  surface showing the figure or its area NAMES it, in D-C51's vocabulary, and that the map names
 *  its ~5-mile ring for the first time. Seven literal edits; no new state key, no new listener,
 *  and one new render value (`compScope`, A48.3). No edit to `MarketMapV3.jsx`: the ring's own
 *  declarations do not change, only the card that now names it.
 *  ------------------------------------------------------------------------------------------ */
const COMP = { date: '2026-09-14', ruling: 'D-C57 (John, 2026-09-14): the map itself names the ~5-mile ring, with ONE legend row in the Market data card while a practice is selected — plus approach A’s label fixes: the "What this means" card names the ZIP area; the selected practice’s competition figure is captioned as an area-apportioned estimate in the D-C51 vocabulary; the paid-employee universe and the withheld-ZIP floor are stated once.' } as const;

/** The two sentences A48.5 and A48.6 append, declared ONCE here and interpolated into both
 *  entries — rule 3 of the spec (§2), enforced at the source rather than by two typists agreeing:
 *  "the same three kinds of figure appear on both surfaces and two wordings of one fact is how
 *  they come to disagree" (A34.7/A34.8's own words). Curly apostrophes, U+2019, as the design's
 *  prose uses throughout. */
const A48_COMPETITION_FOOTNOTE =
  'A practice’s competition figure apportions each ZIP area’s published count to the part of that ZIP within about 5 miles of the practice. '
  + 'A ZIP whose count the Census withheld adds nothing to it, so the figure is a floor rather than an exact count.';

/** A48.1 — the "What this means" card. It named NO area at all ("operate nearby") on a layer whose
 *  legend two lines above says "ZIP Code Tabulation Area", and it said nothing about the universe
 *  the Census counts. One string carries both corrections, because this card is the layer's prose
 *  and is where a property of the DATASET belongs (spec §6.1). The universe sentence is
 *  `app.api.market.EMPLOYER_UNIVERSE` verbatim, pinned across the wire by
 *  `tests/census/test_design_shading_labels.py`, so the integrator's caveat and the buyer's card
 *  read one sentence. The geography phrase is pinned against `SHADING["competition"]["label"]`,
 *  which is the A33.3 mechanism.
 *
 *  UNCHAINED: the line is pristine (`Practice Match V3.rev2.dc.html`), so nothing is consumed.
 *  The card renders the ACTIVE layer's prose and no approved state selects competition, so this
 *  entry moves no existing baseline — `browse-insight-competition` is appended to photograph it. */
const A48_1: Amendment = {
  id: 'A48.1', ...COMP,
  find: '    means: "Establishment counts show how many veterinary businesses operate nearby. They say nothing about size, quality or overlap in services.",\n',
  replace: '    means: "Establishment counts show how many veterinary businesses operate in each ZIP Code Tabulation Area. The Census counts business locations with paid employees, so a practice with no paid staff is not in this figure. They say nothing about size, quality or overlap in services.",\n',
  count: 1
};

/** A48.5 — the docked panel's footnote. TWO sentences APPENDED and nothing rewritten: the
 *  practice's competition figure apportions each ZIP area's published count to the part of that
 *  ZIP inside the ring, and a ZIP the Census withheld adds nothing, so the figure is a FLOOR.
 *  These are properties of the PRACTICE'S FIGURE, which appears on two surfaces, and the "What
 *  this means" card is guaranteed on neither — it is dismissible, it needs competition active,
 *  and it needs a map at least 810 px wide — so the facts go where the figure is (spec §6.2).
 *
 *  CHAINED on A34.7; consumes A34.7, whose whole introduced `<p>` line this rewrites. Every
 *  existing sentence is carried forward byte for byte, A27.4's straight-line sentence and A34.7's
 *  own three-kinds paragraph included. Re-bases `browse-market-panel` and `browse-panel-lightbox`. */
const A48_5: Amendment = {
  id: 'A48.5', ...COMP,
  find: 'Affluence compares this practice’s median income with the US median; growth is the surrounding city or county’s; payroll is the county’s.</p>',
  replace: 'Affluence compares this practice’s median income with the US median; growth is the surrounding city or county’s; payroll is the county’s. '
    + A48_COMPETITION_FOOTNOTE + '</p>',
  count: 1
};

/** A48.6 — the snapshot strip's footnote, A48.5's twin and the SAME two sentences byte for byte.
 *  They also correct, for competition, the generalisation this paragraph makes: "A practice’s
 *  figure is derived from the tracts within about 5 miles of it" is true of four layers and not of
 *  this one, whose units are ZIP areas.
 *
 *  CHAINED on A34.8; consumes A34.8, whose whole introduced `<p>` line this rewrites. A24.20's
 *  growth caveat and the derived-estimates sentence stay byte for byte. Re-bases
 *  `browse-market-strip` and `browse-market-strip-location`. */
const A48_6: Amendment = {
  id: 'A48.6', ...COMP,
  find: 'Population growth is measured for the surrounding city or county, not the tract.</p>',
  replace: 'Population growth is measured for the surrounding city or county, not the tract. '
    + A48_COMPETITION_FOOTNOTE + '</p>',
  count: 1
};
```

and append the block to `amendments()`'s returned array, after `A34_23`:

```ts
    A34_23,
    // A48 — COMP-LABELS (D-C55–D-C58, 2026-09-14). Appended last, as every family is, and it has
    // to be: SIX of the seven are CHAINED on an earlier family's output — A48.2 on A24.8a,
    // A48.3 on A27.6, A48.4 on A34.6, A48.5 on A34.7, A48.6 on A34.8 and A48.7 on A34.16 — so
    // each runs after the entry whose text its `find` takes. A48.1 alone takes a pristine line.
    A48_1, A48_5, A48_6];
```

(Tasks 3–5 insert `A48_7`, `A48_3`/`A48_4` and `A48_2` into this same block at their id positions.)

In `frontend/tests/design-amendments.test.ts`, append the three ids to `AMENDMENT_IDS` with the same comment, and raise `toHaveLength(N)` by 3 — **derive N, do not type it**:

```bash
cd frontend && npx vitest run tests/design-amendments.test.ts -t "exactly the pinned id list" 2>&1 | grep -A2 "toHaveLength"
```

- [ ] **Step 4: Regenerate the design and the port**

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-comp-labels/frontend"
npm run gen:design && npm run gen:logic && npm run gen:app
git diff --stat docs ../docs ../frontend/src 2>/dev/null || git -C .. diff --stat
```

Expected: `Practice Match V3.dc.html`, `logic.js`, `App.vue`, `app.setup.js` change; `pseudo.css` does not (no style changes in this task); `MarketMapV3.jsx` does not.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd frontend && npx vitest run src/logic.test.ts tests/design-amendments.test.ts tests/app-generated.test.ts
cd .. && poetry run pytest tests/census/test_design_shading_labels.py -q
```

Expected: PASS. In particular `design-amendments.test.ts`'s `the amended file is the pristine copy plus exactly the ruled edits` stays green — that is the byte-for-byte proof — and `app-generated.test.ts` proves `App.vue`/`app.setup.js` were regenerated rather than hand-typed.

- [ ] **Step 6: Prove the guards can fail (the house rule)**

```bash
# Perturb the design's own string through the amendment and watch the pins go red.
# Change A48.1's `replace` so it says "Census tract" instead of "ZIP Code Tabulation Area",
# regenerate, and run:
cd frontend && npm run gen:design && npx vitest run src/logic.test.ts -t "names ITS OWN geography"
cd .. && poetry run pytest tests/census/test_design_shading_labels.py::test_the_competition_prose_names_the_geography_that_layer_shades -q
# Expected: BOTH RED. Then revert the perturbation and regenerate before committing.
```

- [ ] **Step 7: Run the full frontend gate and commit**

```bash
cd frontend && npm run typecheck && npm run build && npm test
cd ..
git add frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts frontend/src/logic.test.ts \
        "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
        frontend/src/logic.js frontend/src/App.vue frontend/src/app.setup.js frontend/src/generated/pseudo.css \
        tests/census/test_design_shading_labels.py
git commit -m "feat(design): A48.1/A48.5/A48.6 — the competition prose names its area, its universe and its floor

D-C57 (John, 2026-09-14). Three literal edits. The \"What this means\" card said
\"nearby\" on a layer whose legend two lines above names the ZIP Code Tabulation Area,
and said nothing about the universe ZBP counts — one string carries both corrections,
and the universe sentence is app.api.market.EMPLOYER_UNIVERSE verbatim, pinned across
the wire.

The apportionment and the withheld-ZIP floor are properties of the PRACTICE'S figure,
which appears on two surfaces and beside which the card is guaranteed on neither — so
the two sentences are appended to both footnotes, byte for byte, declared once in the
amendment source. Every existing sentence is carried forward unchanged: A24.20's growth
caveat, A27.4's straight-line sentence, A34.7's three-kinds paragraph.

Consumes A34.7 (A48.5) and A34.8 (A48.6). Ledger rows land in the housekeeping commit.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 3: A48.7 — the snapshot strip's LOCATION caption gains one word

The strip card **already** carries the dataset on its own `src` line ("U.S. Census ZIP Code Business Patterns (2022), NAICS 541940"), so under rule 2 the caption gains one word and nothing else: **`Within about 5 miles of the practice · estimated`**. That is A27.1/A33.1b's own shape — income's caption reads "… · approximate" beside a median derived the same way — and the qualifier is a single word for the same reason: "apportioned by area" is the METHOD, and the method is stated once, in prose (A48.5/A48.6).

**The fallback reads `community level · estimated`.** `locBasis` is `sel.communityLabel || "community level"`, so a place-band listing — and every design fixture, and therefore the approved state — takes the design's fallback word with the new qualifier appended. **That fallback word is out of scope here** (brainstorm §3-A item A7); this spec appends a qualifier to it and does not rule on it.

**One existing test moves and it is named here rather than discovered:** `frontend/src/logic.test.ts`'s A34 case `…and the ONE exemption is the fallback the brief ruled, and only it` asserts that exactly **four** cards' `valueNote` equal the bare string `'community level'`. After this entry the competition card's is `'community level · estimated'`, so the count is **three** and the case must say so — and must assert the competition card's own string, or the exemption it guards would silently stop covering that card.

**Re-basing states, predicted:** `browse-market-strip-location` (the only state with a selection AND the strip open). Measured in Task 6.

**Files:**
- Modify: `frontend/tests/design-amendments.ts` (insert `A48_7` after `A48_6` in the block and in the returned array)
- Modify: `frontend/tests/design-amendments.test.ts` (`AMENDMENT_IDS` + the count)
- Modify: `frontend/src/logic.test.ts` (the new characterisation, and the one existing A34 case)
- Regenerated: the `.dc.html`, `logic.js`, `App.vue`

**Interfaces:**
- Consumes, from Task 2: the A48 block in `amendments()` and the `COMP` ruling constant.
- Produces, for Tasks 6–7: `marketVals(P).stripCards` — the card whose `title` is `LAYER_META.competition.title` (`'Veterinary competition'`) — has `valueNote === "<locBasis> · estimated"` in LOCATION mode and is **unchanged** in AREA mode (`"median of N ZIP areas"`, or `undefined` where the summary has no figure). Amendment id `A48.7` exists; **its ledger row must carry `Consumes A34.16`.**

- [ ] **Step 1: Write the failing test**

Append inside `describe('A48 — …')` in `frontend/src/logic.test.ts`:

```ts
  it('A48.7 — with a practice selected, the competition card is captioned as an estimate', () => {
    const RING = 'Within about 5 miles of the practice';
    const p = (P as unknown as Record<string, unknown>[])
      .filter((x) => x.market === AUSTIN && x.status === 'published')[0];
    const note = (title: string) => c.marketVals(P).stripCards
      .filter((x: { title: string }) => x.title === title)[0].valueNote;

    // ARM 1 — the API served a band label: the card names the ring and the basis, in the design's
    // own ` · ` join. The METHOD is stated once, in prose (A48.5/A48.6); this is the qualifier.
    Object.assign(p, { communityLabel: RING });
    try {
      browse('competition', p.id as string);
      expect(note('Veterinary competition')).toBe(`${RING} · estimated`);
      // …and the OTHER five captions are byte-identical to what they were (the copy-paste catch).
      expect(note('Median household income')).toBe(RING);
      expect(note('Pet ownership (estimated)')).toBe(RING);
      expect(note('Households')).toBe(RING);
      expect(note('Population growth')).toBe('surrounding city or county');
      expect(note('Average practice payroll')).toBe('surrounding county');
    } finally { delete p.communityLabel; }

    // ARM 2 — no served label: the design's own fallback word, with the new qualifier after it.
    // That fallback is a known open item and this ruling does not touch it.
    browse('competition', p.id as string);
    expect(note('Veterinary competition')).toBe('community level · estimated');

    // ARM 3 — AREA mode: nothing changes at all. `locBasis` is "" with no selection, so the
    // competition arm must sit on the LOCATION side of the ternary and nowhere else.
    browse('competition', null);
    const area = note('Veterinary competition');
    expect(area === undefined || /^median of /.test(area as string),
      `AREA mode took the LOCATION arm: "${area}"`).toBe(true);
    expect(String(area)).not.toContain('estimated');
  });
```

And change the ONE existing A34 case (`frontend/src/logic.test.ts`, inside `describe('A34 — one vocabulary…')`, the case titled `'…and the ONE exemption is the fallback the brief ruled, and only it'`) from:

```ts
    expect(notes.filter((n: string) => n === 'community level').length,
      'the no-label fallback is not "community level" any more, so the exemption above is stale').toBe(4);
```

to:

```ts
    // A48.7 (D-C57, 2026-09-14) appends " · estimated" to the COMPETITION card's caption, so that
    // one card now reads "community level · estimated" on this arm. The exemption is unchanged —
    // the fallback WORD is still the design's own, and it is still the one place it may stand —
    // but it is now carried by four cards as a bare string and by one with a basis word after it.
    // Both halves are asserted, because a count alone would stop covering the fifth card.
    expect(notes.filter((n: string) => n === 'community level').length,
      'the no-label fallback is not "community level" any more, so the exemption above is stale').toBe(3);
    expect(notes.filter((n: string) => n === 'community level · estimated').length,
      'the competition card lost A48.7\'s qualifier, or gained the fallback without it').toBe(1);
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd frontend && npx vitest run src/logic.test.ts -t "A48.7" && npx vitest run src/logic.test.ts -t "ONE exemption"
```

Expected: `A48.7 — with a practice selected…` FAILS with `expected 'Within about 5 miles of the practice' to be 'Within about 5 miles of the practice · estimated'`; `…and the ONE exemption…` FAILS with `expected 4 to be 3` (the updated case is red against the unchanged design, which is the proof it is a real gate and not a restatement).

- [ ] **Step 3: Write the amendment entry**

In `frontend/tests/design-amendments.ts`, after `A48_6`:

```ts
/** A48.7 — the snapshot strip's LOCATION caption for the competition card. The card ALREADY names
 *  the dataset, on its own `src` line, so under `metaSource`'s one-string-per-fact rule the caption
 *  gains one word and nothing else: `<area> · estimated`. A27.1/A33.1b's own shape — income's
 *  caption reads "… · approximate" beside a median derived the same way — and the qualifier is a
 *  single word for the same reason: "apportioned by area" is the METHOD, and the method is stated
 *  once, in prose (A48.5/A48.6).
 *
 *  Inserted as a new arm BEFORE the `income` arm of the LOCATION ternary, so `locBasis` — which is
 *  `""` with no selection — cannot reach it: AREA mode keeps "median of N ZIP areas" byte for byte.
 *  CHAINED on A34.16; consumes A34.16, whose own introduced `k === "income"` line this `find` takes
 *  and re-emits unchanged after the new arm.
 *
 *  The fallback reads "community level · estimated" where the API served no label — the design's
 *  own fallback word, which this ruling deliberately does not touch (brainstorm §3-A item A7).
 *  Re-bases `browse-market-strip-location`. */
const A48_7: Amendment = {
  id: 'A48.7', ...COMP,
  find: '                : k === "income" ? (sel.incomeNote ? (sel.incomeNote.indexOf(" · ") > -1 ? sel.incomeNote : locBasis + " · " + sel.incomeNote) : locBasis) : locBasis)\n',
  replace: '                : k === "competition" ? locBasis + " · estimated"\n'
    + '                : k === "income" ? (sel.incomeNote ? (sel.incomeNote.indexOf(" · ") > -1 ? sel.incomeNote : locBasis + " · " + sel.incomeNote) : locBasis) : locBasis)\n',
  count: 1
};
```

Add `A48_7` to the returned array after `A48_6`, and its id to `AMENDMENT_IDS` after `'A48.6'`; raise `toHaveLength` by 1.

- [ ] **Step 4: Regenerate and run**

```bash
cd frontend && npm run gen:design && npm run gen:logic && npm run gen:app
npx vitest run src/logic.test.ts tests/design-amendments.test.ts tests/app-generated.test.ts
```

Expected: PASS, including the A34 block's `with a practice selected every snapshot card names THAT figure's own geography` — it asserts `card.valueNote` **contains** the layer's own geography and that no OTHER ruled geography is named, and `"… · estimated"` satisfies both.

- [ ] **Step 5: Prove the guard can fail**

```bash
# Move A48.7's arm AFTER the `income` arm but before the final `: locBasis)` — the caption is the
# same in LOCATION mode, so a weaker test would still pass. Then delete the arm entirely:
cd frontend && npm run gen:design && npx vitest run src/logic.test.ts -t "A48.7"
# Expected RED on ARM 1. Revert and regenerate.
```

- [ ] **Step 6: Full frontend gate and commit**

```bash
cd frontend && npm run typecheck && npm run build && npm test
cd ..
git add frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts frontend/src/logic.test.ts \
        "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
        frontend/src/logic.js frontend/src/App.vue frontend/src/app.setup.js
git commit -m "feat(design): A48.7 — the snapshot's competition caption says the figure is an estimate

D-C57 (John, 2026-09-14). One literal edit. The strip card already names the dataset on
its own src line, so under metaSource's one-string-per-fact rule the caption gains one
word: \"Within about 5 miles of the practice · estimated\". A27.1/A33.1b's own shape.

The arm sits BEFORE the income arm on the LOCATION side of the ternary, so AREA mode —
where locBasis is \"\" — keeps \"median of N ZIP areas\" byte for byte. Consumes A34.16.

A34's fallback-exemption case moves from four bare \"community level\" captions to three
plus one \"community level · estimated\", asserted on both halves so the exemption does
not stop covering the fifth card.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 4: A48.3 + A48.4 — the docked panel's Competitive Landscape names its area AND its basis

**Where the caption cannot go, measured:** the panel is `width: 366px` with `padding: 16px` → 334 px of content. The Competitive Landscape grid is `1fr 1fr 1fr` with `gap: 6px` → each tile is **107.3 px**; tile padding is 10 px each side and the first two tiles carry a 15 px icon with an 8 px gap, so the text column is **≈ 64 px**. At the tile sub-line's 9.5 px that is about twelve characters. **A caption cannot be a tile sub-line here** and nothing in this task tries to make it one.

**Where it goes:** A34.6's own sub-line under the heading, which is the block's established scope line and runs the full 334 px. It reads `md.panel.overviewScope` today — the same binding as the Market Overview sub-line — and becomes `md.panel.compScope`:

> **`Within about 5 miles of the practice · estimated from ZIP Code Business Patterns 2022`**

The panel names the **dataset** because the panel has no source line of any kind — `metaSource`'s own rule applied one surface over, and decision 13.3.

**The gate is NOT widened** (decision 13.6). `hasOverviewScope` (`!!sel.communityLabel`) is reused unchanged, so where the API served no label the `sc-if` renders no element and the reference and every approved state keep their pixels.

**A48.4's `find` MUST span the "Competitive Landscape" heading.** Measured: the sub-line div occurs **twice** in the amended design, byte-identically — A27.7's copy under "Market Overview" at V3:794 and A34.6's copy here — so a one-line `find` would be ambiguous and `applyAmendments` would throw. That is A34.6's own anchor, for the same reason.

**One existing test moves and it is named here:** `frontend/tests/smoke.spec.ts`'s A34 case `every block of the docked panel says which area it describes…` loops over `['Market Overview', 'Competitive Landscape']` and asserts `beneath.text` is exactly `RING` for both. After A48.4 the second is `RING + ' · estimated from ZIP Code Business Patterns 2022'`.

**Re-basing states, predicted: NONE.** Gated on `hasOverviewScope`, and no design fixture carries a `communityLabel`. Its oracle is the real-browser gate, which is why the smoke case is updated rather than a baseline.

**Files:**
- Modify: `frontend/tests/design-amendments.ts` (`A48_3`, `A48_4`, inserted after `A48_2`'s position and before `A48_5`)
- Modify: `frontend/tests/design-amendments.test.ts` (`AMENDMENT_IDS` + the count)
- Modify: `frontend/src/logic.test.ts` (the characterisation)
- Modify: `frontend/tests/smoke.spec.ts:2325-2333` (the one existing assertion)
- Regenerated: the `.dc.html`, `logic.js`, `App.vue`

**Interfaces:**
- Consumes, from Task 2: the A48 block and `COMP`.
- Produces, for Tasks 5–7: `marketVals(P).panel.compScope` — a string, `"<communityLabel> · estimated from ZIP Code Business Patterns 2022"` where the API served a label and `""` where it did not. `hasOverviewScope` and `overviewScope` are **unchanged** and keep their own reader (the Market Overview sub-line). Amendment ids `A48.3`, `A48.4`; **A48.4's ledger row must carry `Consumes A34.6`.**

- [ ] **Step 1: Write the failing tests**

(a) Append inside `describe('A48 — …')` in `frontend/src/logic.test.ts`:

```ts
  it('A48.3 — the Competitive Landscape sub-line names the ring AND the dataset', () => {
    const RING = 'Within about 5 miles of the practice';
    const p = (P as unknown as Record<string, unknown>[])
      .filter((x) => x.market === AUSTIN && x.status === 'published')[0];

    // The panel has no source line of ANY kind, so this one sub-line carries geography and basis
    // together — `metaSource`'s own rule, one surface over (decision 13.3).
    Object.assign(p, { communityLabel: RING });
    try {
      browse('competition', p.id as string);
      const panel = c.marketVals(P).panel;
      expect(panel.compScope).toBe(`${RING} · estimated from ZIP Code Business Patterns 2022`);
      // …and the Market Overview sub-line is UNTOUCHED: two readers, two strings, one gate.
      expect(panel.overviewScope).toBe(RING);
      expect(panel.hasOverviewScope).toBe(true);
    } finally { delete p.communityLabel; }

    // The gate is NOT widened (decision 13.6): with no served label there is no element at all,
    // which is what keeps every approved state's pixels and all thirteen frozen hashes.
    browse('competition', p.id as string);
    const bare = c.marketVals(P).panel;
    expect(bare.hasOverviewScope).toBe(false);
    expect(bare.compScope, 'the basis was printed with no geography in front of it').toBe('');
    expect(bare.overviewScope).toBe('');
  });
```

(b) In `frontend/tests/smoke.spec.ts`, replace the loop body's scope assertion:

```ts
    // R35-R37 / collision C8: the Competitive Landscape block sat under NO scope line at all —
    // `overviewScope` is rendered once, above the overview grid, and this heading is below it. It
    // takes the Market Overview heading's own sub-line, which is A27.7's established idiom.
    //
    // A48.3/A48.4 (D-C57, 2026-09-14) then widen THAT ONE sub-line — and only it — to name the
    // basis as well as the area, because the panel carries no source line of any kind and the
    // three figures beneath this heading are an area-apportioned estimate. The Market Overview
    // sub-line above keeps the bare label: its grid's figures are the ring's own served values.
    const SCOPE: Record<string, string> = {
      'Market Overview': RING,
      'Competitive Landscape': `${RING} · estimated from ZIP Code Business Patterns 2022`
    };
    for (const heading of Object.keys(SCOPE)) {
      const beneath = await panel.evaluate((root, h) => {
        const head = Array.from(root.querySelectorAll('div')).find((d) => (d.textContent || '').trim() === h);
        const next = head && (head.nextElementSibling as HTMLElement | null);
        return { found: Boolean(head), text: next && (next.textContent || '').trim(), size: next && getComputedStyle(next).fontSize };
      }, heading);
      expect(beneath.found, `the panel has no "${heading}" heading`).toBe(true);
      expect(beneath.text, `"${heading}" names no area — the block beneath it reads as the card's own ring scope without saying so`).toBe(SCOPE[heading]);
      expect(beneath.size, `"${heading}"'s sub-line is not the design's own place-line type`).toBe('12.5px');
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd frontend && npx vitest run src/logic.test.ts -t "A48.3"
```

Expected: FAIL — `expected undefined to be 'Within about 5 miles of the practice · estimated from ZIP Code Business Patterns 2022'` (there is no `compScope` yet).

The smoke case is run in Task 5's Step 6 with the rest of the e2e; run it now if a browser is to hand, and expect `expected 'Within about 5 miles of the practice' to be 'Within about 5 miles of the practice · estimated from ZIP Code Business Patterns 2022'`.

- [ ] **Step 3: Write the two amendment entries**

In `frontend/tests/design-amendments.ts`, between `A48_2`'s slot and `A48_5`:

```ts
/** A48.3 — the one new render value in the whole family. The Competitive Landscape block's scope
 *  line has to say more than the Market Overview block's, because the panel carries NO source line
 *  of any kind and the three figures beneath this heading are an area-apportioned estimate rather
 *  than a served Census value. `metaSource`'s own rule, one surface over (decision 13.3): the
 *  strip card says "· estimated" because its `src` line already names the dataset, and this one
 *  names the dataset itself.
 *
 *  Composed from `sel.communityLabel`, behind A34.6's own `hasOverviewScope` gate UNCHANGED
 *  (decision 13.6) — where the API serves no label the `sc-if` renders no element, so the
 *  reference and every approved state keep their pixels and none of the thirteen frozen hashes
 *  moves. CHAINED on A27.6, whose `overviewScope` line this `find` takes and re-emits unchanged. */
const A48_3: Amendment = {
  id: 'A48.3', ...COMP,
  find: '      overviewScope: sel.communityLabel || "",\n',
  replace: '      overviewScope: sel.communityLabel || "",\n'
    + '      // A48.3 (D-C57): the Competitive Landscape block\'s own scope line. The panel has no\n'
    + '      // source line anywhere, so this one string carries the geography AND the basis; the\n'
    + '      // snapshot strip\'s card says "· estimated" alone because its `src` line already\n'
    + '      // names the dataset. One fact, composed per surface (`metaSource`\'s rule).\n'
    + '      compScope: sel.communityLabel ? sel.communityLabel + " · estimated from ZIP Code Business Patterns 2022" : "",\n',
  count: 1
};

/** A48.4 — the sub-line itself, re-bound from `overviewScope` to A48.3's `compScope`. ONE template
 *  edit and no new markup: A34.6 put this element here and it keeps its declarations, its gate and
 *  its place.
 *
 *  The `find` MUST span the "Competitive Landscape" heading. MEASURED: the sub-line div occurs
 *  TWICE in the amended design, byte-identically — A27.7's copy under "Market Overview" and
 *  A34.6's copy here — so a one-line `find` is ambiguous and `applyAmendments` would throw. That
 *  is A34.6's own anchor, for the same reason. CHAINED on A34.6; consumes A34.6.
 *
 *  No approved state re-bases: the gate is `hasOverviewScope` and the design's fixtures carry no
 *  `communityLabel`. Its oracle is the real-browser gate in `frontend/tests/smoke.spec.ts`. */
const A48_4: Amendment = {
  id: 'A48.4', ...COMP,
  find: '                  <div style="font-family: var(--rf-display); font-size: 14.5px; font-weight: 800; color: var(--vf-navy); margin-top: 18px;">Competitive Landscape</div>\n'
    + '                  <sc-if value="{{ md.panel.hasOverviewScope }}" hint-placeholder-val="{{ false }}">\n'
    + '                    <div style="font-size: 12.5px; color: var(--vf-text); margin-top: 2px;">{{ md.panel.overviewScope }}</div>\n',
  replace: '                  <div style="font-family: var(--rf-display); font-size: 14.5px; font-weight: 800; color: var(--vf-navy); margin-top: 18px;">Competitive Landscape</div>\n'
    + '                  <sc-if value="{{ md.panel.hasOverviewScope }}" hint-placeholder-val="{{ false }}">\n'
    + '                    <div style="font-size: 12.5px; color: var(--vf-text); margin-top: 2px;">{{ md.panel.compScope }}</div>\n',
  count: 1
};
```

Add `A48_3, A48_4` to the returned array in id order (after the `A48_2` slot, before `A48_5`), add `'A48.3', 'A48.4'` to `AMENDMENT_IDS` in the same position, and raise `toHaveLength` by 2.

- [ ] **Step 4: Regenerate and run**

```bash
cd frontend && npm run gen:design && npm run gen:logic && npm run gen:app
npx vitest run src/logic.test.ts tests/design-amendments.test.ts tests/app-generated.test.ts
```

Expected: PASS. `design-amendments.test.ts`'s byte-for-byte case is the proof the two-line ambiguity was resolved — had the `find` been one line, the run would have thrown `A48.4: expected 1 match(es) …, found 2`.

- [ ] **Step 5: Prove the anchor really was ambiguous**

```bash
# Temporarily shorten A48.4's `find` to the sub-line alone and regenerate.
cd frontend && npm run gen:design
# Expected: `A48.4: expected 1 match(es) of "                    <div style=\"font-size: 12.5px;…", found 2`
# Restore the three-line anchor and regenerate.
```

- [ ] **Step 6: Full frontend gate and commit**

```bash
cd frontend && npm run typecheck && npm run build && npm test
cd ..
git add frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts frontend/src/logic.test.ts frontend/tests/smoke.spec.ts \
        "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
        frontend/src/logic.js frontend/src/App.vue frontend/src/app.setup.js
git commit -m "feat(design): A48.3/A48.4 — the panel's Competitive Landscape names its area and its basis

D-C57 (John, 2026-09-14). Two literal edits and the family's one new render value.

The panel carries no source line of any kind, so its scope sub-line has to say what the
strip card's src line says for the strip: \"Within about 5 miles of the practice ·
estimated from ZIP Code Business Patterns 2022\". Measured first: the tile text column
under that heading is ~64 px, about twelve characters at 9.5 px, so a tile sub-line
could never carry it — the block's own scope line can.

The gate is A34.6's own hasOverviewScope, unchanged (decision 13.6), so no approved
state re-bases and no frozen hash moves; the oracle is the real-browser smoke case.
A48.4's find spans the heading because the sub-line div occurs twice, byte-identically.
Consumes A34.6.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 5: A48.2 — the map names its ring

**The gap, exactly.** `MarketMapV3.jsx:214` draws `radius: 8000, color: "#003a70", weight: 1.5, dashArray: "4 4", fill: false, interactive: false` around the selected practice. It has no tooltip, no label and no legend row, so the map has never said what it is or how wide it is. That is the surface the stakeholder's "the area is not defined" lands on squarely.

**Composed from** the Market data card's OWN compare-key row (V3:561–563) and `compareKeyA`'s own swatch declarations — `flex: none; width: 26px; height: 9px; border-radius: 2px; border: 1px solid rgba(0,58,112,.14);` — with the border becoming `1px dashed var(--vf-navy)`: the ring's own colour (`--vf-navy` IS `#003a70`, V3:29) and the design's own dashed-border treatment (V3:855, V3:1050, V3:1345). **There is no dashed-line glyph anywhere in the design to copy**, which is the family's one composition deviation and is decision 13.1. `margin-top` is **11 px**, the legend's own rhythm, not the compare key's 9 px: both values exist in this card and the row sits among the legend's lines, not among Compare's.

**The gate is `md.showDrive` — the same value V3:460 hands the map as `show-drive`**, i.e. A25.6's "no point, no ring" term verbatim. So the row is drawn **exactly when the ring is drawn, by construction**: it cannot claim a ring the map did not paint, and it needs no new state key, no new render value and no new gate. `closePanel` sets `mdSel: null` and A30's `setMarket` sets `mdSel: null`, so in both directions `sel` goes null, `showDrive` goes false, and the ring and the row go together. The row also sits INSIDE the card's own `md.legendOpen` block, so collapsing the card takes it away too — A23's own idiom.

**Width, measured.** The card is `width: 300px` with `padding: 13px 15px 14px` → 270 px of content. Swatch 26 px + gap 5 px = 31 px; the label is 41 characters at 10 px ≈ 197 px. **228 px of 270 px: one line, with room.**

**The phone frame gets no row, and that is MEASURED, not a scope cut.** V3:1524 passes the phone map the same `show-drive="{{ md.showDrive }}"` binding, but **no phone control ever writes `mdSel`**: `mob.selectMarker` (V3:3252) writes `activeId` and, on a second tap, opens the detail. `sel` is `P.filter((x) => x.id === s.mdSel)[0]`, so `showDrive` is false on every phone path and the ring is never drawn there. A row added to the phone sheet's legend (V3:1591–1595) would be **markup that can never render — dead code under the bundle's own rule** (A2.3, A28.5–A28.9). **Record this in the entry's comment and in its ledger row; do NOT "fix" the phone path.** If the phone frame ever gains a docked selection, the row follows it in the same edit.

**Re-basing states, predicted:** `browse-market-panel`, `browse-panel-lightbox`, `browse-market-strip-location` — the only three approved states with a selection. Measured in Task 6.

**Files:**
- Modify: `frontend/tests/design-amendments.ts` (`A48_2`, inserted after `A48_1`)
- Modify: `frontend/tests/design-amendments.test.ts` (`AMENDMENT_IDS`, the count, and the structural case)
- Modify: `frontend/src/logic.test.ts` (the `showDrive` four-quadrant characterisation)
- Modify: `tests/census/test_band_distance.py` (the fifth derivation of the one radius)
- Modify: `frontend/tests/smoke.spec.ts` (the new `test.describe`)
- Regenerated: the `.dc.html`, `logic.js`, `App.vue`, `pseudo.css`

**Interfaces:**
- Consumes, from Task 2: the A48 block and `COMP`. From Task 4: nothing (independent sites).
- Produces, for Tasks 6–7: one new template element in the Market data card's legend, gated on `md.showDrive`, whose text is exactly `About 5 miles around the selected practice`. **No new render value, no new state key, no new listener.** Amendment id `A48.2`; its ledger row needs **no `Consumes` token** — both lines of its `find` are carried forward byte for byte — but it IS chained on **A24.8a** and must run after it.

- [ ] **Step 1: Write the failing tests**

(a) Append inside `describe('A48 — …')` in `frontend/src/logic.test.ts`:

```ts
  it('A48.2 — the legend row\'s gate is the map\'s own "no point, no ring" term', () => {
    // The row is drawn exactly when the RING is drawn, by construction: it binds the same value
    // V3:460 hands the map as `show-drive`, which is A25.6's finite-point term verbatim. The row's
    // PRESENCE is the DOM oracle's and the smoke's job; what is characterised here is the value
    // the markup binds, on all four quadrants that decide it.
    const p = (P as unknown as Record<string, unknown>[])
      .filter((x) => x.market === AUSTIN && x.status === 'published')[0];

    // (1) nothing selected — the panel is closed and there is no ring to name.
    browse('competition', null);
    expect(c.marketVals(P).showDrive).toBe(false);

    // (2) a selected practice with a finite point — the ring is painted, so the row is drawn.
    browse('competition', p.id as string);
    expect(c.marketVals(P).showDrive).toBe(true);

    // (3) a selected practice with NO point (A25: `location_disclosed` defaults false, so the API
    //     serves lat/lng null). No pin, no ring — and now no row claiming one.
    const lat = p.lat; const lng = p.lng;
    Object.assign(p, { lat: null, lng: null });
    try {
      browse('competition', p.id as string);
      expect(c.marketVals(P).showDrive, 'a row claimed a ring the map did not paint').toBe(false);
      // …and a NaN is not a null: `Number.isFinite`, never `!= null` (A25's own measurement).
      Object.assign(p, { lat: Number.NaN, lng: Number.NaN });
      browse('competition', p.id as string);
      expect(c.marketVals(P).showDrive).toBe(false);
    } finally { Object.assign(p, { lat, lng }); }

    // (4) closing the panel takes it away, and so does a metro change (A30's `mdSel: null`).
    browse('competition', p.id as string);
    c.marketVals(P).closePanel();
    expect(c.marketVals(P).showDrive).toBe(false);
    browse('competition', p.id as string);
    c.setMarket('Sacramento, CA');
    expect(c.marketVals(P).showDrive, 'a metro change left the ring key over a practice in another city').toBe(false);
  });
```

> **The call shapes above are measured at `ac1b34e` and are the ones the file already uses.** A13.1 made `setMarket` a class property that takes a bare value OR a change event (`c.setMarket('Sacramento, CA')` and `c.setMarket({ target: { value: 'Atlanta, GA' } })` are both in `describe("A30 — a metro change closes the docked panel…")`), and `closePanel` is a member of `marketVals`' own return. The design's fixture metros are Austin, Sacramento, Orlando and Atlanta — there is no Dallas in `MARKETS`. If `main` has moved either shape, copy whatever the A30 block uses; the assertion is what matters.

(b) Append to `frontend/tests/design-amendments.test.ts`:

```ts
  it('A48.2 adds ONE ring key row, composed from the card\'s own compare key, and none on the phone', () => {
    const amended = readFileSync(AMENDED, 'utf8');
    const ROW = '<span style="display: inline-flex; align-items: center; gap: 5px;"><span style="flex: none; width: 26px; height: 9px; border-radius: 2px; border: 1px dashed var(--vf-navy);"></span>About 5 miles around the selected practice</span>';
    // ONE row, on the desktop legend only. The phone sheet's legend gets none: `mob.selectMarker`
    // writes `activeId` and never `mdSel`, so `showDrive` is false on every phone path and the
    // markup could never render — dead code under the bundle's own rule.
    expect(amended.split(ROW).length - 1, 'the ring key row is not in the design exactly once').toBe(1);
    expect(amended.split('value="{{ md.showDrive }}"').length - 1, 'showDrive gates exactly one sc-if — the row\'s').toBe(1);
    // The swatch's BOX is the compare key's own, declaration for declaration; only the border
    // changes, to the design's own dashed treatment in the ring's own colour (`--vf-navy` is
    // `#003a70`, which is what MarketMapV3.jsx draws the ring in).
    expect(amended).toContain('flex: none; width: 26px; height: 9px; border-radius: 2px; border: 1px solid rgba(0,58,112,.14);');
    expect(amended.split('1px dashed var(--vf-navy)').length - 1, 'A48.2 introduces exactly one dashed navy border').toBe(1);
    // It sits between the geography line and the source line, inside the card's own legendOpen
    // block, so collapsing the card takes it away with everything else (A23's idiom).
    const legend = amended.split('{{ md.active.geoLine }}')[1].split('{{ md.active.sourceLine }}')[0];
    expect(legend, 'the row is not between the geography line and the source line').toContain(ROW);
    // No new state key and no new render value: the gate is the value the MAP already takes.
    expect(amended.split('show-drive="{{ md.showDrive }}"').length - 1, 'the map\'s own two bindings are untouched').toBe(2);
  });
```

(c) Append to `tests/census/test_band_distance.py`:

```python
def test_the_maps_own_legend_row_names_the_distance_the_pipeline_buffers_at():
    """A48.2 (D-C57, John 2026-09-14) — the FIFTH derivation of the one radius.

    Until this row the map drew an unlabelled dashed circle and said nothing about it, which is
    the surface the stakeholder's "the area is not defined" landed on. The row names the distance,
    so the distance has to come from the same authority the ring's radius does: change
    `BANDS["drive_10"]` and this fails here instead of leaving the map naming a distance it does
    not draw -- exactly what the four cases above already do for the card, the app's ring and the
    design's ring.

    "About", capital A: the row captions a GLYPH and says which practice the circle belongs to,
    where `BAND_LABEL` captions a FIGURE (decision 13.2). The NUMBER is what is pinned."""
    amended = (ROOT / "docs" / "design-reference" / "design_handoff_practice_match_v3"
               / "Practice Match V3.dc.html").read_text(encoding="utf-8")
    row = f"About {_miles()} miles around the selected practice"
    assert row in amended, (
        f"the Market data card's ring key row does not name {_miles()} miles — "
        f"BANDS['drive_10'] is {BANDS['drive_10']} m and the map would label a ring it does not draw"
    )
    assert amended.count(row) == 1, "the ring is named once in the design, not twice"
```

(d) Append to `frontend/tests/smoke.spec.ts`, at the end of the file:

```ts
test.describe('A48.2 — the map names its ring, and only while it draws one (D-C57)', () => {
  const KEY = 'About 5 miles around the selected practice';

  test('a selected practice puts the ring key in the legend, and closing the panel takes it away', async ({ page }) => {
    await prepare(page);
    const errors = trapErrors(page);
    await signInAs(page, 'design', '/browse');
    await waitMap(page);

    // Nothing selected: no ring, no key. This is the state `browse` itself photographs.
    await expect(page.getByText(KEY)).toHaveCount(0);

    await page.getByText('Cedar Park').first().click();
    const panel = page.locator('div.rf-scroll[style*="width: 366px"]');
    await panel.getByRole('button', { name: 'View full listing' }).waitFor({ state: 'visible' });
    await expect(page.getByText(KEY).first()).toBeVisible();

    // …and it goes with the ring. `closePanel` sets `mdSel: null`, which is the same term
    // `showDrive` reads, so the two cannot disagree.
    await panel.getByRole('button', { name: 'Close panel' }).click();
    await expect(page.getByText(KEY)).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test('a metro change takes it away too — A30\'s path, which the row now shares', async ({ page }) => {
    await prepare(page);
    const errors = trapErrors(page);
    await signInAs(page, 'design', '/browse');
    await waitMap(page);
    await page.getByText('Cedar Park').first().click();
    await expect(page.getByText(KEY).first()).toBeVisible();

    // A30 (Task PANEL-STALE): `setMarket` writes `mdSel: null`, so the panel closes, the ring
    // goes and the key goes with it. Reached exactly as `browse-metro-menu` reaches the same
    // control — a COMBOBOX, not a button, for A13's own reason (ARIA 1.2 supports
    // `aria-activedescendant` on `combobox`; `button` is not among the roles that carry it).
    const trigger = page.getByRole('combobox', { name: 'Metro area' });
    const current = (await trigger.innerText()).trim();
    await trigger.click();
    const metro = page.getByRole('listbox', { name: 'Metro area' });
    await metro.waitFor({ state: 'visible' });
    // The metro list is the API's, not the design's — `load.ts` prunes `MARKETS` to what
    // `/api/markets` served — so the OTHER city is read off the list rather than typed, and a
    // database seeded with one metro fails loudly here instead of walking a path that is not there.
    const names = (await metro.getByRole('option').allInnerTexts()).map((s) => s.trim());
    const other = names.find((n) => n !== current);
    expect(other, `the seeded database serves one metro (${names.join(', ')}), so this path cannot be walked`).toBeTruthy();
    await metro.getByRole('option', { name: other as string, exact: true }).click();
    await expect(page.getByText(KEY)).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test('the phone frame draws no ring and shows no key', async ({ page }) => {
    // MEASURED, and recorded rather than fixed: V3:1524 hands the phone map the SAME
    // `show-drive` binding, but `mob.selectMarker` writes `activeId` and never `mdSel`, so `sel`
    // is undefined on every phone path and `showDrive` is false. A row in the phone sheet's
    // legend would be markup that can never render — dead code under the bundle's own rule
    // (A2.3, A28.5–A28.9) — so A48.2 adds none. This case is what would go red if the phone
    // frame ever gained a docked selection, which is when the row follows it.
    await prepare(page);
    const errors = trapErrors(page);
    await signInAs(page, 'design', '/browse?viewport=mobile');
    await waitMap(page);
    await expect(page.getByText(KEY)).toHaveCount(0);
    expect(errors).toEqual([]);
  });
});
```

> **Every locator above is the one the tree already uses, measured at `ac1b34e`.** `browse-metro-menu` (`screens.ts`) reaches the metro control as `getByRole('combobox', { name: 'Metro area' })` with `getByRole('listbox', { name: 'Metro area' })`; `signInAs(page, 'design', '/browse?viewport=mobile')` is how `smoke.spec.ts` already reaches the phone frame (D-I8-7); and `page.getByText('Cedar Park').first().click()` is how the A31 block already selects a practice against the REAL API, unstubbed — these three cases deliberately do **not** stub `/api/listings`, because what they prove is that the row appears over a real listing with a real point.

> **`waitMap`, `prepare`, `signInAs` and `trapErrors` are `smoke.spec.ts`'s own helpers** and are already imported at the top of that file; add nothing to the import line.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd frontend && npx vitest run src/logic.test.ts -t "A48.2" && npx vitest run tests/design-amendments.test.ts -t "A48.2"
cd .. && poetry run pytest tests/census/test_band_distance.py -q
```

Expected:
- vitest `A48.2 — the legend row's gate…` **PASSES** already — it characterises `showDrive`, which exists; that is deliberate and is the proof the gate is the design's own, not something this family invents. **Run it and record the pass**; the entry's own red is the next one.
- vitest `A48.2 adds ONE ring key row…` FAILS: `the ring key row is not in the design exactly once: expected 0 to be 1`
- pytest FAILS: `the Market data card's ring key row does not name 5 miles — BANDS['drive_10'] is 8000 m and the map would label a ring it does not draw`

- [ ] **Step 3: Write the amendment entry**

In `frontend/tests/design-amendments.ts`, immediately after `A48_1`:

```ts
/** A48.2 — THE MAP NAMES ITS RING. `MarketMapV3.jsx:214` draws `radius: 8000, color: "#003a70",
 *  weight: 1.5, dashArray: "4 4", fill: false, interactive: false` around the selected practice
 *  and has never had a tooltip, a label or a legend row, so the map never said what the circle is
 *  or how wide it is — the surface the stakeholder's "the area is not defined" lands on squarely.
 *
 *  COMPOSED from the Market data card's OWN compare-key row (the 26 × 9 swatch box plus a 5 px
 *  gap inside a 12 px flex row at 10 px) and the design's own dashed-border treatment, in the
 *  ring's own colour: `--vf-navy` IS `#003a70`, so the swatch names no colour the design does not
 *  already own, and an unfilled dashed outline is what the ring actually is. THERE IS NO DASHED
 *  GLYPH ANYWHERE IN THE DESIGN to copy, which is this family's one composition deviation and is
 *  John's decision 13.1 — the alternative, a filled square in the ring colour, was rejected
 *  because a solid `--vf-navy` block in a legend whose other swatches are choropleth classes reads
 *  as a sixth class in a colour no ramp carries. `margin-top` is 11 px, the legend's own rhythm
 *  (the geo line and the source line either side of it), not the compare key's 9 px.
 *
 *  THE GATE IS `md.showDrive` — the SAME value V3:460 hands the map as `show-drive`, i.e. A25.6's
 *  "no point, no ring" term verbatim — so the row is drawn exactly when the ring is drawn, by
 *  construction, and cannot claim one the map did not paint. No new state key, no new render
 *  value, no new listener. `closePanel` and A30's `setMarket` both write `mdSel: null`, so in both
 *  directions the ring and the row go together; and the row sits inside the card's own
 *  `legendOpen` block, so collapsing the card takes it too (A23's idiom).
 *
 *  THE PHONE SHEET GETS NO ROW, MEASURED: V3:1524 passes the phone map the same binding, but
 *  `mob.selectMarker` writes `activeId` and NEVER `mdSel`, so `sel` is undefined on every phone
 *  path and `showDrive` is false there. A row in the phone legend would be markup that can never
 *  render — dead code under the bundle's own rule (A2.3, A28.5–A28.9). If the phone frame ever
 *  gains a docked selection, the row follows it in the same edit.
 *
 *  The `find` is the two-line pair (`hasGeo`'s closing `</sc-if>` and the `sourceLine` div) so the
 *  anchor is unambiguous; both lines are re-emitted byte for byte, so nothing is consumed. CHAINED
 *  on A24.8a, which introduced both. The DISTANCE is pinned to `app.census.catchment.BANDS`
 *  through `tests/census/test_band_distance.py` — the fifth derivation of the one radius — so the
 *  map can never name a distance it does not draw. Re-bases `browse-market-panel`,
 *  `browse-panel-lightbox` and `browse-market-strip-location`. */
const A48_2: Amendment = {
  id: 'A48.2', ...COMP,
  find: '                    </sc-if>\n'
    + '                    <div style="margin-top: 11px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.sourceLine }}</div>\n',
  replace: '                    </sc-if>\n'
    + '                    <sc-if value="{{ md.showDrive }}" hint-placeholder-val="{{ false }}">\n'
    + '                      <div style="display: flex; gap: 12px; margin-top: 11px; font-size: 10px; color: var(--vf-text);">\n'
    + '                        <span style="display: inline-flex; align-items: center; gap: 5px;"><span style="flex: none; width: 26px; height: 9px; border-radius: 2px; border: 1px dashed var(--vf-navy);"></span>About 5 miles around the selected practice</span>\n'
    + '                      </div>\n'
    + '                    </sc-if>\n'
    + '                    <div style="margin-top: 11px; font-size: 10.5px; line-height: 1.55; color: #767676;">{{ md.active.sourceLine }}</div>\n',
  count: 1
};
```

Add `A48_2` to the returned array between `A48_1` and `A48_3`, add `'A48.2'` to `AMENDMENT_IDS` in the same position, and raise `toHaveLength` by 1.

- [ ] **Step 4: Regenerate and run the unit gates**

```bash
cd frontend && npm run gen:design && npm run gen:logic && npm run gen:app
npx vitest run src/logic.test.ts tests/design-amendments.test.ts tests/app-generated.test.ts
cd .. && poetry run pytest tests/census/test_band_distance.py tests/census/test_design_shading_labels.py -q
```

Expected: PASS. `pseudo.css` may change (a new inline-styled element); `app-generated.test.ts` is what proves it was generated.

- [ ] **Step 5: Prove the radius pin can fail**

```bash
# Change BANDS["drive_10"] to 16000 in app/census/catchment.py and run:
cd .. && poetry run pytest tests/census/test_band_distance.py -q
# Expected: FIVE failures, the new one reading
#   "the Market data card's ring key row does not name 10 miles — BANDS['drive_10'] is 16000 m…"
# Revert the radius. This is the whole point of the fifth derivation.
```

- [ ] **Step 6: Run the smoke case against the real API**

```bash
export PW_APP_PORT=5593 PW_REF_PORT=5594 PW_CS_PORT=5595 PW_API_PORT=8167
export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match_complabels
export REDIS_URL=redis://localhost:6380/11
for p in 5593 5594 5595 8167; do lsof -nP -iTCP:$p -sTCP:LISTEN && { echo "PORT $p BUSY"; exit 1; }; done
docker compose -f docker-compose.dev.yml up -d
cd frontend && npx playwright test --config=tests/playwright.config.ts --project=app smoke.spec.ts -g "A48.2|A34 — one vocabulary"
```

Expected: PASS — the three new A48.2 cases and, with Task 4's edit already in, the updated A34 panel-scope case.

- [ ] **Step 7: Full frontend gate and commit**

```bash
cd frontend && npm run typecheck && npm run build && npm test
cd ..
git add frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts frontend/src/logic.test.ts \
        frontend/tests/smoke.spec.ts tests/census/test_band_distance.py \
        "docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html" \
        frontend/src/logic.js frontend/src/App.vue frontend/src/app.setup.js frontend/src/generated/pseudo.css
git commit -m "feat(design): A48.2 — the Browse map names its ~5-mile ring, in one legend row

D-C57 (John, 2026-09-14). MarketMapV3.jsx:214 has drawn an unlabelled dashed circle at
8 000 m with no tooltip and no legend row since V3, so the map never said what the
circle is — the surface the stakeholder's question landed on. One template insertion in
the Market data card's legend, between its geography line and its source line.

Composed from the card's OWN compare-key row and swatch box, with the border becoming
the design's own dashed treatment in the ring's own colour (--vf-navy is #003a70).
There is no dashed glyph in the design to copy: that is the family's one composition
deviation and John's decision 13.1.

The gate is md.showDrive — the same value V3:460 hands the map as show-drive, A25.6's
\"no point, no ring\" term — so the row is drawn exactly when the ring is, by
construction. No new state key, no new render value, no new listener.

The phone sheet gets no row and that is measured: mob.selectMarker writes activeId and
never mdSel, so showDrive is false on every phone path and the markup could never
render. Recorded, not fixed.

The distance joins tests/census/test_band_distance.py as the fifth derivation of the
one radius, so the map can never name a distance it does not draw.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 6: The oracle — one state appended, the re-base set measured, the frozen thirteen proved unmoved

A ruled copy change that nothing photographs is the D-C40 / A26-F2 gap, and **A48.1 is exactly that**: the "What this means" card renders `md.active.means` for the layer in force, and no approved state selects competition. One state is appended, in `browse-layer-households`'s own shape — the existing precedent for a state that selects a layer.

**The re-base set is MEASURED, not reasoned** (A33's discipline): the pre-change baseline hashes were taken in Preconditions; this task regenerates and diffs. The prediction is **four movers** — `browse-market-panel`, `browse-panel-lightbox` (A48.2 + A48.5), `browse-market-strip` (A48.6), `browse-market-strip-location` (A48.2 + A48.6 + A48.7) — plus the appended state, which has no predecessor. **A fifth mover is a NEEDS_CONTEXT, not a re-pin.**

**Files:**
- Modify: `frontend/tests/screens.ts` (append `browse-insight-competition` at the end of `SCREENS`)
- Test: `frontend/tests/reference-baselines.spec.ts` (no edit — it emits one test per `SCREENS` entry), `visual.spec.ts`, `dom.spec.ts`, `baseline-manifest.test.ts`

**Interfaces:**
- Consumes, from Tasks 2–5: all seven A48 entries applied, the design regenerated.
- Produces, for Task 7: `SCREENS.length` is one greater than it was; **CLAUDE.md's Layout line must name the new count** (`the N approved states`), which `tests/test_docs.py::test_claude_md_approved_screen_count_matches_screens_ts` enforces.

- [ ] **Step 1: Append the approved state**

At the END of `SCREENS` in `frontend/tests/screens.ts`, after `browse-market-strip-location`:

```ts
  // A48.1 (Task COMP-LABELS, ruling D-C57, 2026-09-14) — the "What this means" card's own prose,
  // which no approved state has ever photographed: the card renders `md.active.means` for the
  // layer in force and no state selects competition. That is the D-C40 / A26-F2 gap, and a ruled
  // copy change with no oracle is exactly what this list exists to close. D-C40's precedent
  // (`browse-market-strip`): appending one Browse state moves no frozen hash, none of the
  // thirteen being a Browse capture.
  //
  // Reached the way `browse-layer-households` reaches the same control — click the unlabelled
  // layer trigger, wait for the listbox, click the row by its own NAME, so a layer added to or
  // removed from the catalogue fails this loudly instead of silently photographing its neighbour.
  // The card is then waited for by ITS OWN NEW SENTENCE rather than by a bare settle: `insightOpen`
  // needs a value layer, an undismissed card, an expanded legend, no open Compare and a map column
  // of at least 810 px, and a timeout cannot tell "the card is open" from "the click no-opped on
  // both targets" — which is how a state goes on photographing the wrong screen in silence (M9).
  { name: 'browse-insight-competition', steps: async (p) => {
    await browse(p);
    await layerTrigger(p).first().click();
    const menu = p.getByRole('listbox', { name: 'Active market layer' });
    await menu.waitFor({ state: 'visible' });
    await menu.getByRole('option', { name: 'Veterinary competition' }).click();
    await menu.waitFor({ state: 'detached' });
    await p.getByText('The Census counts business locations with paid employees').first().waitFor({ state: 'visible' });
    // …and it is IN THE FRAME, whole. The card is `position: absolute; bottom: 22px` and grows
    // UPWARD as the prose lengthens (about three lines becoming six at 324 px of content), under
    // the Market data card's own `z-index: 600` container — so a taller card passes beneath the
    // legend rather than over it, and this is the assertion that fails if it ever does not fit.
    await expect(p.getByText('The Census counts business locations with paid employees').first()).toBeInViewport({ ratio: 1 });
    await p.waitForTimeout(400);
  } },
```

- [ ] **Step 2: Regenerate the baselines and measure the movers**

```bash
export PW_APP_PORT=5593 PW_REF_PORT=5594 PW_CS_PORT=5595 PW_API_PORT=8167
export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match_complabels
export REDIS_URL=redis://localhost:6380/11
docker compose -f docker-compose.dev.yml up -d
cd frontend && npm run test:visual:baselines
node -e '
const {createHash}=require("crypto"), {readdirSync,readFileSync}=require("fs"), {join}=require("path");
const before=JSON.parse(readFileSync(process.env.PRE,"utf8"));
const d="tests/visual.spec.ts-snapshots", after={};
for (const f of readdirSync(d).sort()) after[f]=createHash("sha256").update(readFileSync(join(d,f))).digest("hex");
const moved=Object.keys(before).filter(f=>before[f]!==after[f]);
const added=Object.keys(after).filter(f=>!(f in before));
const gone=Object.keys(before).filter(f=>!(f in after));
console.log("baselines:",Object.keys(after).length);
console.log("MOVED:",moved); console.log("ADDED:",added); console.log("REMOVED:",gone);
'
```

Expected, exactly:

```
baselines: <one more than Preconditions recorded>
MOVED: [ 'browse-market-panel-darwin.png',
         'browse-market-strip-darwin.png',
         'browse-market-strip-location-darwin.png',
         'browse-panel-lightbox-darwin.png' ]
ADDED: [ 'browse-insight-competition-darwin.png' ]
REMOVED: []
```

**Anything else is a NEEDS_CONTEXT.** A fifth mover means an A48 entry reached a surface the spec did not predict; a missing mover means an entry did not reach the surface it was written for.

- [ ] **Step 3: Prove the frozen thirteen did not move**

```bash
cd frontend && node tests/baseline-manifest.mjs --check
npx vitest run tests/baseline-manifest.test.ts
```

Expected: exit 0, and `expect(UNCHANGED_SCREENS).toHaveLength(13)` green, with no `moved` list. **`--check` never writes; `--write` is not run in this task and there is no ruling for it.** If a hash moved: STOP with NEEDS_CONTEXT — do not re-pin.

- [ ] **Step 4: Look at the four new baselines and the appended one**

```bash
open frontend/tests/visual.spec.ts-snapshots/browse-insight-competition-darwin.png \
     frontend/tests/visual.spec.ts-snapshots/browse-market-panel-darwin.png \
     frontend/tests/visual.spec.ts-snapshots/browse-market-strip-darwin.png \
     frontend/tests/visual.spec.ts-snapshots/browse-market-strip-location-darwin.png
```

Check by eye, and report each in the hand-back:
1. `browse-insight-competition` — the "What this means" card carries all three sentences, is **whole in the frame**, and passes **beneath** the Market data card rather than over it (the card is `z-index: 590` against the legend container's `600`, and the legend runs `top: 16px; bottom: 72px` in the same 16 px column).
2. `browse-market-panel` — the ring key row is one line, sits between the geography line and the source line, and its dashed swatch reads as an outline rather than as a class.
3. `browse-market-strip` — the footnote's two new sentences are whole in the frame (the state scrolls to it and asserts `toBeInViewport({ ratio: 1 })`).
4. `browse-market-strip-location` — the competition card's caption reads `Within about 5 miles of the practice · estimated` **on two lines, with the card's height unmoved** (47 characters at ≈ 34 per line, against today's 35). If the card grew, say so — the pixel diff is the proof, not the spec's paragraph.

- [ ] **Step 5: Run the pixel gate, the DOM oracle and the smoke**

```bash
cd frontend && npm run test:e2e
```

Expected: the whole `app` project green — `visual.spec.ts` at `maxDiffPixels: 0` against the freshly generated baselines, `dom.spec.ts` (the DOM oracle, which runs under neither `test:smoke` nor `test:visual`), `smoke.spec.ts` including Task 5's three new cases and Task 4's updated one, plus `account-flows`, `listing-flows`, `signin-form`, `capture-determinism` and `boundary-flows`.

**A visual failure AFTER regeneration means the app and the design diverged** — stop and diff `App.vue` against the `.dc.html`; never widen the tolerance.

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/tests/screens.ts
git commit -m "test(oracle): browse-insight-competition — the ruled prose gets a photograph

D-C40's own mechanism. A48.1 rewrites LAYER_META.competition.means and the \"What this
means\" card renders the ACTIVE layer's prose, so no approved state had ever
photographed it — the gap A26-F2 closed for the More-filters popover, one surface over.

Reached in browse-layer-households' own shape and waited for by the card's own new
sentence rather than a settle, so the state cannot photograph a click that no-opped.

MEASURED re-base, baselines regenerated before and after and PNG hashes diffed: exactly
four approved states move — browse-market-panel, browse-panel-lightbox,
browse-market-strip, browse-market-strip-location — and one is added. None of
baseline-manifest.json's thirteen frozen hashes moves; none of them is a Browse capture.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Task 7: The ledger, the document, the gates, the push

Seven `LOCAL_AMENDMENTS.md` rows, the citation re-map, both copies of CLAUDE.md's counts, one CLAUDE.md paragraph for A48 in the established voice, the four-part gate, and the push to both remotes with CI read rather than assumed.

**Files:**
- Modify: `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md`
- Modify: `CLAUDE.md` (the A48 paragraph, the counts sentence in **both** copies of the "Source of truth" block, and the Layout line's approved-state count)
- Modify: `frontend/tests/citation-pins.json` **only if `remap:citations` refuses** — and then with a reason, never a hand edit to a citation

**Interfaces:**
- Consumes, from Tasks 2–6: seven amendment ids, the appended state, the measured re-base set.
- Produces: nothing later depends on.

- [ ] **Step 1: Merge `main` FIRST**

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-comp-labels"
git fetch origin && git merge origin/main
```

Amendment branches collide on the ledger gates. If `main` has moved, resolve `design-amendments.ts`, `design-amendments.test.ts` and `LOCAL_AMENDMENTS.md` by **keeping both families' entries in id order**, re-run `npm run gen:design && npm run gen:logic && npm run gen:app`, and **re-take every derived count below after the merge**. If a family id collides with A48, STOP.

- [ ] **Step 2: Write the seven ledger rows**

Append to `LOCAL_AMENDMENTS.md`'s table, **in apply order** (A48.1, A48.2, A48.3, A48.4, A48.5, A48.6, A48.7), in the ledger's four columns (`Id | Date | John's ruling | What changes`). The ruling column carries D-C57 in his relayed words. **Four rows carry a consumption token** — A48.4 (`Consumes A34.6`), A48.5 (`Consumes A34.7`), A48.6 (`Consumes A34.8`), A48.7 (`Consumes A34.16`) — and the token goes on the CONSUMER's own row, spelled as the word, never as a bare mention.

The two that carry the most, written out in full so the voice is not guessed at:

> **A48.2** | 2026-09-14 | D-C57 (John, 2026-09-14): the map itself names the ~5-mile ring, with one legend row in the Market data card while a practice is selected. | One template insertion — the Market data card's legend gains a key row between its geography line (V3:503) and its source line, composed from the card's OWN compare-key row and `compareKeyA`'s 26 × 9 swatch box, with the box's `1px solid rgba(0,58,112,.14)` border becoming `1px dashed var(--vf-navy)` — the ring's own colour (`--vf-navy` is `#003a70`, V3:29) and the design's own dashed-border treatment; there is no dashed glyph in the design to copy, which is recorded as the family's one composition deviation and is John's decision 13.1 (the alternative, a filled square in the ring's colour, reads as a sixth choropleth class in a colour no ramp carries). The gate is `md.showDrive` — the SAME value V3:460 hands the map as `show-drive`, i.e. A25.6's "no point, no ring" term — so the row is drawn exactly when the ring is drawn and cannot claim one the map did not paint; `closePanel` and A30's `mdSel: null` both take it away with the ring, and the row sits inside the card's own `legendOpen` block so collapsing the card takes it too (A23's idiom). `margin-top` is 11 px, the legend's own rhythm, not the compare key's 9 px. No new state key, no new render value, no new listener. Root cause: `MarketMapV3.jsx:214` draws the ring `interactive: false` with no tooltip and no legend row, so the map had never named the area a buyer was being shown. The phone sheet's legend gets no row: V3:1524 passes the same binding, but `mob.selectMarker` writes `activeId` and never `mdSel`, so `showDrive` is false on every phone path and the markup could never render — dead code under the bundle's own rule. The distance is pinned to `app.census.catchment.BANDS["drive_10"]` by `tests/census/test_band_distance.py`, the fifth derivation of the one radius. Re-bases `browse-market-panel`, `browse-panel-lightbox`, `browse-market-strip-location`; none of the thirteen frozen hashes is a Browse capture.

> **A48.5** | 2026-09-14 | D-C57 (John, 2026-09-14): the paid-employee universe and the withheld-ZIP floor are stated once. | One template literal — the docked panel's footnote, **Consumes A34.7**. TWO sentences APPENDED and no rewrite: the practice's competition figure apportions each ZIP area's published count to the part of that ZIP within about 5 miles of the practice, and a ZIP whose count the Census withheld adds nothing to it, so the figure is a floor rather than an exact count. Every existing sentence is carried forward byte for byte, A27.4's straight-line sentence and A34.7's three-kinds paragraph included — the fix-round-3 lesson AMEND-GUARD exists for. The same two sentences appear on the strip footnote (A48.6) byte for byte, declared once in `design-amendments.ts` rather than typed twice, which is A34.7/A34.8's own rule: the same figure appears on both surfaces and two wordings of one fact is how they come to disagree. "Said once" means one wording, not one location — A34.8's own recorded holding — and the card whose prose states the DATASET's universe (A48.1) is guaranteed on neither surface, being dismissible, needing competition active and needing a map at least 810 px wide. Re-bases `browse-market-panel` and `browse-panel-lightbox`.

The other five follow the same shape: what the entry changes, why, what it is composed from, what is carried forward, its consumption token where it has one, and which approved states re-base.

- [ ] **Step 3: Re-map the citations**

```bash
cd frontend && npm run remap:citations
```

Expected: it prints what it moved and exits 0. **A48.2, A48.5 and A48.6 add lines to the bundle**, so every `V3:<line>` citation below them moves; the tool re-takes them all. If it **refuses** rather than guesses, the answer is a row in `frontend/tests/citation-pins.json` naming the line by a neighbouring distinctive anchor and saying WHY — never a hand edit to a citation.

```bash
npx vitest run tests/design-amendments.test.ts
```

Expected: green, including the two citation cases and `amend-guard`'s ruled-text findings (`findings: []`).

- [ ] **Step 4: Prove AMEND-GUARD can fail on this family**

```bash
# Delete the words "Consumes A34.7" from A48.5's ledger row and run:
cd frontend && npx vitest run tests/design-amendments.test.ts -t "amend-guard"
# Expected RED, naming the pair:
#   A34.7 -> A48.5: "…</p>" left the design and no LOCAL_AMENDMENTS.md row of an entry that TAKES
#   it declares it — the entry that takes a line says it consumes A34.7
# Restore the token. Repeat for A48.6/A34.8 if a second proof is wanted.
```

- [ ] **Step 5: Re-take every derived count and write them into CLAUDE.md**

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-comp-labels"
python3 - <<'PY'
import re, pathlib
ts = pathlib.Path("frontend/tests/design-amendments.ts").read_text()
test_ts = pathlib.Path("frontend/tests/design-amendments.test.ts").read_text()
md = pathlib.Path("docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md").read_text()
screens = pathlib.Path("frontend/tests/screens.ts").read_text()
lits = re.findall(r"id: 'A(\d+)", ts)
a1 = int(re.search(r"Array\.from\(\{ length: (\d+) \}, \(_, i\) => `A1\.\$\{i \+ 1\}`\)", test_ts).group(1))
rows = len(re.findall(r"^\|\s*(A[\w.]+)\s*\|", md, re.M))
print("literals:", len(lits))
print("families:", len({int(n) for n in lits}) + 1, "(+1 for A1, derived not literal)")
print("entries  :", len(lits) + a1, f"(A1's {a1} derived edits plus {len(lits)} literals)")
print("ledger rows:", rows, "expected", len(lits) + 1)
print("A48 entries:", len({i for i in re.findall(r"id: 'A48(?:\.[^']+)?'", ts)}) or len(re.findall(r"id: 'A48", ts)))
print("approved states:", len(re.findall(r"^\s*\{ name: '", screens, re.M)))
PY
```

Expected at `ac1b34e` + this branch (**re-derive after the merge — these are the deltas, not the truth**): literals `327 + 7 = 334`; families `34 + 1 = 35` → the word **Thirty-five**; entries `334 + 24 = 358`; ledger rows `335`; A48 entries `7`; approved states `55 + 1 = 56`.

Then edit `CLAUDE.md`:

1. **Both copies** of the sentence `Thirty-four families, 351 entries: A1's 24 derived edits plus 327 literals` become the re-derived one. The paragraph is duplicated in the file; `grep -c` it first and fix **every** occurrence — `tests/test_docs.py::test_claude_md_amendment_family_and_entry_counts_match_design_amendments` checks the phrase is present and its sibling checks that the neighbouring wrong numbers are **not**, so a stale second copy fails the pair.
   ```bash
   grep -c "Thirty-four families, 351 entries" CLAUDE.md          # expect 2 before the edit
   grep -c "A1's 24 derived edits plus 327 literals" CLAUDE.md     # expect 2 before the edit
   ```
2. The **Layout** line's `the 55 approved states` becomes `the 56 approved states` (`test_claude_md_approved_screen_count_matches_screens_ts`).
3. **One A48 paragraph, in the established voice, appended to the amendment sequence in both copies of the block** — `test_claude_md_amendment_paragraph_has_a_prose_section_for_every_family` requires a `**A48**` marker for the new family, and `test_claude_md_literal_edit_clauses_count_each_family_s_own_entries` requires its literal-edit clause to state **seven**. Draft:

> **A48** (John's rulings D-C55–D-C58, 2026-09-14 — Task COMP-LABELS, on the stakeholder's own question: "one of the options is veterinary competition, and it looks like it's the number of practices in a given area, but the area is not defined"). D-C56 confirms **D-C44**: no ring toggle and no 5/10-mile chooser, and D-C58 leaves state premises registers a research spike with no screen. What D-C57 rules is that every surface showing a competition figure or its area NAMES it, in D-C51's vocabulary, and that the map names its ring for the first time. **Seven literal edits.** The map's own gap was the plainest: `MarketMapV3.jsx:214` draws a dashed 8 000 m circle `interactive: false` with no tooltip, no label and no legend row, so a buyer was shown an area the product never described — A48.2 adds ONE key row to the Market data card's legend, between its geography line and its source line, composed from the card's own compare-key row and `compareKeyA`'s 26 × 9 swatch box with the border becoming `1px dashed var(--vf-navy)` (the ring's own colour: `--vf-navy` IS `#003a70`), because **there is no dashed glyph anywhere in the design to copy** — the family's one composition deviation, ruled rather than assumed, against a filled square that would read as a sixth choropleth class in a colour no ramp carries. Its gate is `md.showDrive`, the SAME value the map itself takes as `show-drive` and A25.6's "no point, no ring" term verbatim, so the row is drawn exactly when the ring is drawn, by construction — no new state key, no new render value, no new listener — and `closePanel`, A30's `setMarket` and A23's collapse each take it away with the ring. The phone sheet gets none, MEASURED: `mob.selectMarker` writes `activeId` and never `mdSel`, so `showDrive` is false on every phone path and the markup could never render (dead code under the bundle's own rule), which is recorded rather than fixed. The two "said once" facts are split by what they are properties OF: the paid-employee universe is the DATASET's, so A48.1 puts it on the "What this means" card — which also stopped saying "nearby" and names the ZIP Code Tabulation Area it shades — as `app.api.market.EMPLOYER_UNIVERSE` verbatim, one sentence pinned across the wire; and the apportionment and the withheld-ZIP floor are the PRACTICE FIGURE's, which appears on two surfaces beside which that card is guaranteed on neither, so A48.5 and A48.6 append the same two sentences to the docked panel's footnote and the snapshot strip's, **byte for byte and declared once in the amendment source** ("said once" means one wording, not one location — A34.8's own holding), with every existing sentence carried forward including A24.20's growth caveat and A27.4's straight-line sentence. The selected practice's own figure is then captioned per surface, `metaSource`'s rule: A48.7 gives the snapshot card `· estimated` alone because its `src` line already names the dataset, and A48.3/A48.4 give the panel's Competitive Landscape sub-line `· estimated from ZIP Code Business Patterns 2022` because the panel has no source line of any kind — measured first, the tile text column under that heading is about 64 px, twelve characters at 9.5 px, so no tile sub-line could ever have carried it. The panel's gate stays A34.6's `hasOverviewScope`, so a listing served no `community_label` keeps today's behaviour and no approved state re-bases for it; the strip's fallback takes `community level · estimated`, the design's own fallback word this ruling deliberately does not touch. **No new API field and no new route** (spec §7): the radius is already one number in four places and the legend row joins that same pin as a fifth, and the apportionment is a constant of the pipeline the design states itself. FOUR approved states re-base — `browse-market-panel`, `browse-panel-lightbox`, `browse-market-strip`, `browse-market-strip-location` — measured the A33 way rather than reasoned, and `browse-insight-competition` is appended because A48.1's prose is a ruled copy change nothing photographed, the D-C40 / A26-F2 gap. None of `baseline-manifest.json`'s thirteen frozen hashes moves; none of them is a Browse capture. THE HONEST MEASURE: this names the area on every surface that shows the number, and the number itself is unchanged — it is still an area-apportioned estimate from ZIP-code counts, still a floor wherever the Census withheld one, and **there is still no count of practices within a radius a member can choose**, which is approach B and is ruled out by D-C56.

- [ ] **Step 6: Run the document gates**

```bash
poetry run pytest tests/test_docs.py -q
```

Expected: green — the family/entry counts in both copies, the discrimination case, the ledger row count, the per-family literal-edit clause, the prose-section-per-family case and the approved-state count.

- [ ] **Step 7: Run the full four-part verification gate**

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-comp-labels"

# (1a) backend, exactly as CI
docker compose -f docker-compose.dev.yml up -d
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m "not timing"
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m timing -p no:randomly --cov-append --cov-report=xml --cov-fail-under=100
poetry run ruff check . && poetry run mypy app --strict

# (1b) frontend, BUILD BEFORE TEST, exactly as CI
cd frontend && npm run typecheck && npm run build && npm test

# (2) oracles from V3, then visual + DOM + smoke
export PW_APP_PORT=5593 PW_REF_PORT=5594 PW_CS_PORT=5595 PW_API_PORT=8167
export DATABASE_URL=postgresql://pm:pm_dev_pw@localhost:5433/practice_match_complabels
export REDIS_URL=redis://localhost:6380/11
npm run test:visual:baselines && npm run test:e2e
node tests/baseline-manifest.mjs --check
```

Expected: all green; `--check` exits 0 with no `moved` list.

- [ ] **Step 8: Commit and push to BOTH remotes**

```bash
cd "/Users/johndean/Development/Practice Match/.worktrees/feat-comp-labels"
git add docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md CLAUDE.md frontend/tests/citation-pins.json 2>/dev/null || \
git add docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md CLAUDE.md
git commit -m "docs(design): the A48 ledger rows, the re-mapped citations and CLAUDE.md's derived counts

Seven rows for family A48 (D-C55–D-C58, John, 2026-09-14), in apply order, with the
four consumption tokens the AMEND-GUARD line tier reads — Consumes A34.6 (A48.4),
A34.7 (A48.5), A34.8 (A48.6), A34.16 (A48.7). A48.2, A48.5 and A48.6 add lines to the
bundle, so every V3: citation below them is re-mapped by npm run remap:citations in
this same commit.

CLAUDE.md: the A48 paragraph in the established voice, and the family/entry/literal
counts and the approved-state count re-taken from the tree in BOTH copies of the
\"Source of truth\" block.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"

git push origin feat/comp-labels
git push production feat/comp-labels
```

- [ ] **Step 9: Read CI on the pushed SHA — foreground, bounded, never assumed**

A subagent receives no background notification, so the wait is an explicit foreground loop:

```bash
SHA=$(git rev-parse HEAD)
for i in $(seq 1 40); do
  OUT=$(gh run list --branch feat/comp-labels --commit "$SHA" --json name,status,conclusion 2>/dev/null)
  echo "[$i] $OUT"
  case "$OUT" in *'"status":"in_progress"'*|*'"status":"queued"'*|'[]') sleep 30 ;; *) break ;; esac
done
gh run list --branch feat/comp-labels --commit "$SHA" --json name,status,conclusion
```

**Read the conclusions; do not assume them.** All four Quality jobs must be `success`. 0.1.21 shipped with the Quality workflow red because a local gate weaker than CI was trusted — that is why `npm test` above is `vitest run --coverage` and not a bare `vitest run`.

- [ ] **Step 10: Hand back**

Report, in this order: the base SHA and the pushed SHA; the four Quality conclusions as read; the measured re-base set from Task 6 Step 2 verbatim; `node tests/baseline-manifest.mjs --check`'s exit; the re-derived counts from Step 5; the five screenshots from Task 6 Step 4 with the eye-check on each; and the **one judgement that wants John's eye**, stated plainly: the ring swatch is **composed from two existing declarations rather than copied from one existing glyph, because no dashed glyph exists in the design** — decision 13.1, taken per the spec's recommendation, and a one-value change to A48.2 if he prefers the filled square.

**Do NOT merge, do NOT deploy, do NOT run `railway`.** The QA click-through (select a practice on Browse and read the ring key; open the layer menu and choose Veterinary competition; open the snapshot strip in both modes), the production smoke, the lockstep version bump and the release are the controller's.

---

## Known gaps, recorded rather than hidden

- **The panel footnote is not rendered on the panel's other tabs or on its `noDemo` branch**, so A48.5's two sentences are absent there while the ring key row is still on the map beside them. Recorded in the spec (§4) and not papered over: a second wording of one fact is the thing this ruling exists to prevent.
- **The `"community level"` fallback word** (brainstorm §3-A item A7) is the one place a `<word> level` geography may still stand; A48.7 appends a qualifier to it and rules nothing about it.
- **The Low / Moderate / High competition thresholds** (1.4 and 2.2 per 10 000 households, `frontend/src/logic.js`) are stated nowhere a member can read them. Named in the brainstorm as item A5, not in D-C57's list, a one-sentence footnote change whenever John wants it.
- **The layer-menu option's bare title** ("Veterinary competition") is left alone deliberately: it is the title element for all six layers, the legend directly beneath it names the geography, and a six-row change for one layer's complaint is not surgical.
- **The map tip's "Counted within this…" sentence is not widened.** Its subject is the polygon under the cursor, and the paid-employee universe is a property of the dataset, not of that polygon.
- **A31.14 (`feat/snap-metro`) touches the same two paragraphs A48.5 and A48.6 append to.** Whichever lands second re-anchors its `find` against the other's output and declares the consumption. A48 first is the recommendation: it is a copy-only change with no route behind it, and A31.14 is not written.

---

## Self-review

Run against the spec with fresh eyes after writing. Findings, and what was done about each.

**1. Spec coverage.**

| Spec section | Task |
|---|---|
| §3 S1 (legend, new ring row) | 5 |
| §3 S2 (map tip — unchanged) | recorded in Known gaps; no entry, as §3 rules |
| §3 S3 (drawer row — unchanged) | recorded in the A48 paragraph; no entry |
| §3 S4 ("What this means") | 2 (A48.1) |
| §3 S5 (strip LOCATION caption) | 3 (A48.7) |
| §3 S6 (panel sub-line + footnote) | 4 (A48.3/A48.4), 2 (A48.5) |
| §4 (row composition, gate, swatch, phone, width) | 5, in the entry comment and the ledger row |
| §5.1 / §5.2 (the two measured captions) | 4, 3 |
| §6.1 / §6.2 (said once) | 2 |
| §7 (no new field; `EMPLOYER_UNIVERSE`; contract doc) | 1 |
| §8 (family A48, seven entries, chaining) | Preconditions + 2–5 |
| §9 (oracle plan, re-bases, frozen thirteen) | 6 |
| §10 tests 1–9 | 1 (7, 9), 2 (1, 5, 6), 3 (4), 4 (3), 5 (2, 8), 6 (visual/DOM), 5+6 (smoke) |
| §12 (order) | recorded above as the controller's sequencing; §12.1 (release 0.1.25 first) and §12.2/§12.3 (branch sequencing) are controller actions, and Global Constraint (l) carries the merge rule |
| §13 (six decisions) | all six recorded as taken, at the head |

**No gap found.** §12.1's "release 0.1.25 to QA and production first" is deliberately NOT a task: it is a controller action outside this branch, and Global Constraint (h) forbids the implementer touching a version.

**2. Placeholder scan.** No "TBD", no "implement later", no "similar to Task N", no "add appropriate error handling". Every code step carries the code, and the first draft's three "check the spelling before running" deferrals were all closed by measurement rather than left as instructions: `setMarket` takes a bare value or a change event and the design's metros are Austin / Sacramento / Orlando / Atlanta (there is no Dallas in `MARKETS`, which the draft's test had assumed); the metro control is `getByRole('combobox', { name: 'Metro area' })` with a listbox of the same accessible name, and the phone frame is `signInAs(page, 'design', '/browse?viewport=mobile')`; and `test_contract_doc.py`'s path constant is `DOC`, not `ROOT`, with `app.api.market` imported **inside** the test function under that module's own recorded ruling. The one remaining conditional instruction — "if `main` has moved either shape, copy whatever the A30 block uses" — is a rot guard, not a gap: the code is given in full.

**3. Type and name consistency.** Checked across tasks:
- `EMPLOYER_UNIVERSE` — Task 1 defines it, Task 2 embeds the same sentence and pins it; one spelling, and the pin is what enforces that.
- `compScope` — Task 4 produces it (A48.3), Task 4 binds it (A48.4); `overviewScope` and `hasOverviewScope` are named as **unchanged** in both, and the logic test asserts all three together so a rename cannot be half-done.
- `showDrive` — Task 5 consumes it and defines nothing; the amendment test asserts it gates exactly one `sc-if` and that the map's two `show-drive` bindings are untouched.
- `locBasis` — Task 3 reads it; Global Constraint (f) records that it is `""` (not `undefined`) in AREA mode, which is why the new arm is on the LOCATION side, and the test's ARM 3 is what proves it.
- `A48_COMPETITION_FOOTNOTE` — declared once in Task 2 and interpolated into both A48.5 and A48.6, so rule 3's "byte for byte on both surfaces" is enforced at the source rather than by two typists agreeing.
- Amendment ids `A48.1`–`A48.7` are used consistently, in id order in `amendments()` and in `AMENDMENT_IDS`, with the four consumption tokens named identically in the entry comments (Tasks 2–5) and in the ledger rows (Task 7).

**4. Two things the spec left implicit, resolved inline rather than propagated.**
- **Spec §9's "`STRIP_FOOTNOTE` in `screens.ts` … is updated in the same commit as A48.6, or `browse-market-strip` hangs".** Measured at `ac1b34e`: `STRIP_FOOTNOTE` is `'In AREA mode each card is the median across the metro’s Census tracts'`, which sits in the MIDDLE of the paragraph, and A48.6 **appends** — so the waiter's substring survives untouched and no edit is needed. What does need watching is that the taller paragraph still satisfies `toBeInViewport({ ratio: 1 })`; Task 6 Step 4 makes that an explicit eye-check on the regenerated baseline, and a failure there is a NEEDS_CONTEXT rather than a tolerance change. **No `screens.ts` edit for A48.6.**
- **Spec §8.2's chaining column shows "—" for A48.2 and A48.3.** Measured: neither `find` occurs in the pristine bundle (A48.2's is A24.8a's output, A48.3's is A27.6's), so both are ORDER-chained even though neither consumes a line — each re-emits what it takes byte for byte. The Preconditions block makes that measurement the first thing the implementer runs, and both entry comments say which predecessor they ride.

**5. One test-scope call worth naming.** Task 2's new pytest walks `LAYER_META.competition.means` **only**. Swept over all six it would fail today on `households` ("in each community") and `econ` ("market-level") — prose about what a figure is FOR, which D-C57 did not rule on. The docstring says so, so the narrowing is a recorded decision and not an oversight.
