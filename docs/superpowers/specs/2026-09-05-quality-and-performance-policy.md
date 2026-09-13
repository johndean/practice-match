# Practice Match — Quality and Performance Policy (all sub-projects)

**Date:** 2026-09-05 · **Owner:** John · **Applies to:** every plan (Platform, Census, Map engines, Google, SP2 and later). Each plan's Global Constraints point here; the gates below are CI-enforced, not advisory.

## 1. Test shape and ratio

Target shape — roughly **70 % unit · 20 % integration · 10 % end-to-end** by count, enforced through the rules below rather than by counting:

| Layer | What it proves | Where | Rule |
|---|---|---|---|
| Unit | Pure functions, adapters against stubs (Leaflet/Google stubs, `httpx.MockTransport`), formulas, eligibility rules, formatters | `tests/**/test_*.py` (no DB), `frontend/src/**/*.test.ts` | Every function or method that contains a branch has a unit test; every bug fix starts with a failing unit test |
| Integration | Migrations, SQL, Celery tasks, FastAPI endpoints against the scratch database and Redis | `tests/census`, `tests/api`, `tests/test_*.py` with the `conn`/`client` fixtures | Every endpoint has an API test for the success path, every 4xx it defines, and its auth gate; every migration has a schema test |
| End-to-end | Screen states against the approved design, route smoke, engine no-mixing, live verification | Playwright projects `app`, `reference`, `app-google`; `scripts/verify-*.sh` | Every screen state in `screens.ts` is compared at `maxDiffPixels: 0`; every deploy is verified by a tested script |
| Characterisation | The untouched prototype (`logic.js`) | `frontend/src/logic.test.ts` | RED is a deliberate broken expectation; the prototype is the oracle |
| Drift | Docs, config, CI, contracts | `tests/test_docs.py`, `tests/test_build_config.py`, `tests/api/test_contract_doc.py` | Documentation that can drift from code is tested against the code |

## 2. "Bug/error free" — the gates that block a merge or a promotion

| Gate | Command (CI job) | Threshold |
|---|---|---|
| Backend tests | `poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-report=xml --cov-fail-under=100` | 0 failures, 0 warnings, 100 % line AND branch coverage of `app/` and `scripts/` (raised in P14, 2026-09-07, from the earlier 90 % line-coverage gate over `app/` alone, once the two standing gaps — `app/db.py`'s other-loop disposal arm and `scripts/migrate.py`'s `__main__` guard — were covered); John's ruling 2026-09-06 is the authority for the 100 % figure itself, backend and frontend alike |
| Changed-line coverage | `diff-cover coverage.xml --compare-branch=origin/main --fail-under=100` | 100 % of changed lines covered (PRs) |
| Types and lint (backend) | `poetry run ruff check app tests scripts && poetry run mypy app --strict` | 0 findings |
| Frontend tests | `npx vitest run --coverage` (scope and thresholds live in the vitest config) | 0 failures; **100 % lines, branches, functions and statements on every hand-written frontend file** (`src/**` minus the generated `App.vue`/`generated/**`, the untouched prototype `logic.js`/`dc-logic.js`/`lib/**`, type-only files and test helpers — those stay under the visual, DOM and characterisation gates). *Raised from 85 % by John on 2026-09-06.* |
| Types (frontend) | `npx vue-tsc --noEmit` with `"strict": true` | 0 errors |
| Browser errors | Playwright harness (`prepare()`) registers `page.on('pageerror')` and `page.on('console', msg => msg.type() === 'error')` and fails the test on any occurrence | 0 page errors, 0 console errors in every e2e run |
| Visual gate | `npx playwright test --project=app` | every state passes at `maxDiffPixels: 0` |
| Shell scripts | `bash tests/scripts/*.sh` | all print OK |
| Secrets | `gitleaks detect` | 0 findings |
| Deploy | `scripts/verify-deploy.sh <ENV>` then the smoke project against the live host | must pass before promotion; a failure on production triggers the DEPLOY.md rollback (redeploy the previous image tag) |

**Task CI-TIMING (2026-09-12).** The Backend tests row above is unchanged as a RULE — the same
coverage, the same 100 % threshold — but the ONE `poetry run pytest` invocation it names now runs
in two steps, not one: real wall-clock budget tests (three constant-time auth checks and eleven
p95 latency gates, `@pytest.mark.timing`, registered in `pyproject.toml`) measured the loaded
developer machine rather than the code when scheduled beside CPU-heavy neighbours, so they are
pulled out of the normal run and into a second, serial, LAST step, their coverage appended onto
the first step's so `--cov-fail-under=100` still reads one combined report:

```
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m "not timing"
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov=tests/e2e -m timing -p no:randomly --cov-append --cov-report=xml --cov-fail-under=100
```

Neither budget is widened or skipped; only WHEN they run moves. `tests/test_timing_marker.py` is
the RED-first proof that every test asserting a real wall-clock budget carries the marker, checked
against the whole suite rather than a hand-typed list of names.

**Fix round 2 correction (2026-09-12).** The paragraph above said "three constant-time auth checks
and eleven p95 latency gates" — the accurate composition of the fourteen is four constant-time auth
checks, eight `gate_p95` latency gates, one DB-timeout probe and one Argon2id duration check, per
`tests/test_timing_marker.py`'s own docstring. Also from that round: `test_timing_marker.py`'s
"checked against the whole suite" is now literally true — it was checked against a hand-picked
four-module list until this round, which a throwaway fifth-module test proved blind before the fix
and caught after it (see the report).

## 3. "Always fast" — performance budgets, enforced

| Budget | Test | Threshold |
|---|---|---|
| API latency (in-process, scratch DB, warm) | `tests/perf/test_api_latency.py` — 50 sequential requests per endpoint through the ASGI client after warm-up; asserts p95 — when the first p95 is over budget the endpoint is measured once more and the second decides (a regression fails twice; a stalled shared runner does not), both sample sets printed | `/api/healthz` ≤ 20 ms · `/` (rendered shell) ≤ 15 ms · `/api/layers`, `/api/map-config`, `/api/markets` ≤ 100 ms · `/api/markets/{cbsa}/communities`, `/api/listings/{id}/market` (cached) ≤ 150 ms · `/api/admin/data-sources` ≤ 150 ms |
| Shell render | `tests/test_shell.py::test_render_index_is_string_work_only` — 1,000 renders from a fixed snapshot | ≤ 2 ms mean; no I/O (patched `_load_snapshot` must not be called) |
| Hot queries use indexes | `tests/perf/test_query_plans.py` — `EXPLAIN (FORMAT JSON)` on the `market_metric` panel lookup, the `practice_location` CBSA join and the `dataset_registry` active-engine lookup | plan contains an `Index Scan`/`Index Only Scan` and no `Seq Scan` on the large table |
| Bundle size | `frontend/tests/bundle-budget.test.ts` — gzip sizes of `dist/_app/*.js` after `npm run build` | main bundle ≤ 220 KB gz · `engine-leaflet` ≤ 60 KB gz · `engine-google` ≤ 12 KB gz · total JS on first load ≤ 300 KB gz |
| First map paint (e2e, stubs) | Playwright: time from `goto` to `[data-map]` present | ≤ 1,500 ms local/CI |
| No request on the critical path | Map engines M7 | engine chunk request starts before the app bundle finishes |
| Live QA load smoke (nightly) | `scripts/k6-smoke.js` via `.github/workflows/perf.yml` (schedule `0 6 * * *`), 20 virtual users, 2 minutes | p95 ≤ 400 ms on the read endpoints (health only until SP2), error rate 0 %, no 5xx |
| Google spend | Quotas + budget (Google plan G1) | daily caps; $50/month alert |

Budgets are numbers in tests. Raising a budget is a reviewed change with a reason in the commit message, never a silent edit.

## 4. Where each gate is created

| Gate | Plan task |
|---|---|
| CI jobs, coverage, diff-cover, ruff, mypy, vue-tsc, gitleaks, shell tests | Platform Task 9 (`quality.yml`), extended by later plans as they add tests |
| `pageerror`/`console.error` fail rule; first-map-paint budget | Platform Task 3 (`harness.ts`), Task 4 (smoke) |
| `tests/perf/test_api_latency.py` (healthz, shell) | Platform Task 5; endpoints appended by Census B5 and Map engines M3/M4 |
| `frontend/tests/bundle-budget.test.ts` | Platform Task 1 (main bundle), Map engines M5 (engine chunks) |
| `tests/perf/test_query_plans.py` | **Created** by identity Task I9a (the admin review queue's two `migrations/015` indexes, and the session lookup), then extended by Census B5 (panel/communities) and Map engines M1 (active-engine lookup) as their tables land. *(Row corrected 2026-09-07: the file predates B5/M1 because Wave 2a needed it first; the §5 harness below is unchanged, its `active_engine` Seq-Scan exemption included, so M1's entry is one row in `PLANS`.)* |
| Shell render micro-benchmark | Map engines M2 |
| `scripts/k6-smoke.js`, `perf.yml` | Platform Task 10 |
| Rollback procedure | Platform Task 9 (`DEPLOY.md`) |

## 5. Test code for the shared gates

`tests/perf/test_api_latency.py` (the endpoint list grows per plan; the harness is written once):
```python
import statistics
import time

import pytest

BUDGET_MS = {"/api/healthz": 20, "/": 15}   # Census B5 and Map engines M3/M4 extend this dict in their tasks


async def p95(client, path: str, n: int = 50) -> float:
    await client.get(path)  # warm-up
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        r = await client.get(path)
        samples.append((time.perf_counter() - t0) * 1000)
        assert r.status_code < 500, path
    return statistics.quantiles(samples, n=20)[18]


@pytest.mark.parametrize("path, budget", sorted(BUDGET_MS.items()))
async def test_p95_within_budget(client, path, budget):
    assert await p95(client, path) <= budget, f"{path} p95 over {budget} ms"
```

`frontend/tests/bundle-budget.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { gzipSync } from 'node:zlib';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const DIST = join(import.meta.dirname, '..', 'dist', '_app');
const gz = (f: string) => gzipSync(readFileSync(join(DIST, f))).length / 1024;
const files = () => readdirSync(DIST).filter((f) => f.endsWith('.js'));

describe('bundle budgets (KB gzipped)', () => {
  it('main bundle ≤ 220', () => { expect(gz(files().find((f) => f.startsWith('index-'))!)).toBeLessThanOrEqual(220); });
  it('engine-leaflet ≤ 60, engine-google ≤ 12', () => {
    const l = files().find((f) => f.startsWith('engine-leaflet-')); const g = files().find((f) => f.startsWith('engine-google-'));
    if (l) expect(gz(l)).toBeLessThanOrEqual(60);
    if (g) expect(gz(g)).toBeLessThanOrEqual(12);
  });
  it('first-load JS ≤ 300', () => {
    const first = files().filter((f) => f.startsWith('index-') || f.startsWith('engine-leaflet-'));
    expect(first.reduce((s, f) => s + gz(f), 0)).toBeLessThanOrEqual(300);
  });
});
```

`tests/perf/test_query_plans.py`:
```python
import json

import pytest

PLANS = {
    "panel": ("EXPLAIN (FORMAT JSON) SELECT * FROM market_metric WHERE listing_id = %s AND band = 'place'", ("00000000-0000-0000-0000-000000000000",)),
    "active_engine": ("EXPLAIN (FORMAT JSON) SELECT dataset_key FROM dataset_registry WHERE kind = 'engine' AND active", ()),
}


def _node_types(plan):
    out = [plan.get("Node Type")]
    for child in plan.get("Plans", []):
        out += _node_types(child)
    return out


@pytest.mark.parametrize("name", sorted(PLANS))
def test_hot_query_uses_an_index(conn, name):
    sql, params = PLANS[name]
    with conn.cursor() as cur:
        cur.execute(sql, params)
        plan = cur.fetchone()[0][0]["Plan"]
    types = _node_types(plan)
    assert any("Index" in t for t in types), types
    assert "Seq Scan" not in types or name == "active_engine", types   # the registry is ~20 rows; a seq scan there is fine
```

`scripts/k6-smoke.js`:
```js
import http from 'k6/http';
import { check } from 'k6';
export const options = { vus: 20, duration: '2m', thresholds: { http_req_duration: ['p(95)<400'], http_req_failed: ['rate==0'] } };
const BASE = __ENV.BASE_URL;
// Until Sub-project 2 ships its read endpoints (/api/layers, /api/map-config, /api/markets) only the
// health endpoint exists; the four-endpoint list and the member token return with SP2 (John, 2026-09-06).
export default function () {
  for (const p of ['/api/healthz']) {
    const r = http.get(`${BASE}${p}`);
    check(r, { 'status < 500': (x) => x.status < 500 });
  }
}
```

Harness rule (Platform Task 3 `prepare()`):
```ts
page.on('pageerror', (e) => { throw new Error(`page error: ${e.message}`); });
page.on('console', (m) => { if (m.type() === 'error') throw new Error(`console.error: ${m.text()}`); });
```
