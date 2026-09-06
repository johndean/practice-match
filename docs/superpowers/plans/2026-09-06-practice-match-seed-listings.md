# Seed Listings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the design's twenty-one anonymised fixture practices on qa.foundation.vin with **eighteen seeded demo hospitals** — John's names, real mapable street addresses, fake `555` phone numbers, opening hours and photographs — stored in a new `listing` table, served by three `listing.read`-guarded endpoints, and read by the Vue app at start-up.

**Architecture:** Four artefacts move, in order. (1) `migrations/015_listing.sql` creates the `listing` table Wave 2b and the Census plan's Phase B build on. (2) `seeds/hospitals.json` carries John's eighteen rows verbatim, plus the fields the design needs that his table does not carry, plus coordinates the implementer geocodes **once** through the U.S. Census Bureau Geocoder and commits with the match tier. (3) `scripts/prepare_photos.py` turns John's curated photograph folders into committed WebP files under `seeds/hospitals/photos/`, and `scripts/seed_listings.py` (the new `seed` role of `scripts/start.sh`) upserts the rows into any environment's database. (4) `app/api/listings.py` serves them and `frontend/src/listings/load.ts` replaces the generated `P` / `MARKETS` fixture arrays in place, **keeping every field name the design's template reads**. The pixel gates keep running against a stub built from the design's own fixtures, so the zero-tolerance visual suite is unaffected; only QA sees the eighteen.

**Tech Stack:** PostgreSQL 16 + PostGIS 3.5 (`geography(Point,4326)`, GiST) · FastAPI + psycopg2 (`app.db.sync_conn`) · Redis (`app.cache.sync_redis`, 60 s list cache) · `app.auth.deps.require("listing.read")` from Wave 2a · Pillow (the one new dependency, dev group only) · Vue 3 + TypeScript 6 · Playwright 1.63 · Vitest 3.

**Branch:** worktree `feat/seed-listings` cut from `main` **after** Browse V3 and Wave 2a Task I4 have both merged (see Preconditions). It merges to `main` before the rest of Wave 2b.

---

## Global Constraints

Every task's requirements implicitly include this section.

### The spec's decisions, verbatim (`docs/superpowers/specs/2026-09-06-seed-listings-design.md` §3)

- **D1 — Placement and order.** A plan of its own, executed after Browse V3 merges (it rewrites the Browse rail, pins and detail) and after Wave 2a Task I4 merges (it needs `require`), and before the rest of Wave 2b. It defines the `listing` table that Wave 2b and the Census plan's Phase B build on: `id uuid`, `slug`, `name`, `street`, `city`, `state`, `zip`, `phone`, `hours`, `status`, `location_disclosed`, `geom geography(Point,4326)`, the design's card and detail fields (`area`, `type`, `price`, `rev`, `docs`, `rooms`, `sqft`, `bldg`, `est`, `listed_at`, `note`, `staff`, `services`, `facility`, `ownership`, `market`), `photos jsonb`, `source` (`seed` | `seller`), timestamps. Migrations start at `015` (identity uses `010`–`014`; the Census plan's Phase B stays at `060`+).
- **D2 — Geocoding.** Addresses are geocoded once, offline, by the implementer through the **U.S. Census Bureau Geocoder** (public domain, no key, no Google), and the coordinates are committed in `seeds/hospitals.json` with the geocoder's match tier as provenance. A test asserts every point lies inside its state's bounding box and within 25 km of its city's centroid. No Google Places or Google Geocoding content is stored (standing rule).
- **D3 — Photos.** `scripts/prepare_photos.py` reads the curated folders, keeps up to **four** photographs per hospital in folder order, converts each to WebP at ≤ 1600 px on the long edge and ≤ 250 KB, strips metadata, and writes `seeds/hospitals/photos/<slug>/1.webp … 4.webp` plus an inventory (`seeds/hospitals/photos/index.json` with SHA-256s). The outputs are committed (≈ 15 MB; the repository is public — John supplied these photographs for the demo hospitals). They are served by the API, not bundled into the frontend, through `GET /api/listings/{id}/photos/{n}` (`listing.read`), so an unpublished or anonymised listing's photographs are never public.
- **D4 — Fields John's table does not carry.** `type` is derived from the name ("Specialist" → Specialty; "ER" / "Critical Care" / "24/7 emergency" hours → Emergency; otherwise Small animal); `price`, `rev`, `docs`, `rooms`, `sqft`, `bldg`, `est`, `staff`, `services`, `facility`, `ownership` are plausible demo values set per hospital in `seeds/hospitals.json` (visible, editable by John at any time, marked `"demo": true`); `note` reads "Demo listing seeded by the VIN Foundation." Community figures (`pop`, `growth`, `income`, `hh`) are left null until the Census plan supplies them; the UI shows its existing empty state for them.
- **D5 — Names follow the design.** The design anonymises listings on cards (area and type, no name). The hospital name is stored and shown wherever the V3 design has a title slot (the detail screen and the Admin Listings tab in Wave 2b); cards keep the design's anonymised layout. **→ John:** say "show names on cards" to change the design instead.
- **D6 — The pixel gate stays honest.** The visual, DOM-oracle and smoke gates run against a stubbed `/api/listings` that returns the design's own fixture practices, so every pixel still matches the V3 design file; QA runs against the seeded eighteen. The frontend loads listings from the API at start-up and replaces the generated `P`/market arrays **keeping their field names** (the CLAUDE.md launch-removal note); the fixture arrays remain in the generated file until Wave 2a's `convert-dc.mjs --launch` strips them.
- **D7 — Removal of the existing listings.** `scripts/seed_listings.py` is idempotent (upsert by `slug`) and `--reset` deletes every `source='seed'` row first; on QA the eighteen replace the design fixtures entirely. It runs inside the api container (`railway ssh`, John's ed25519 key) or as the `seed` role of `scripts/start.sh`; never on production without John's go.
- **D8 — Access.** `GET /api/listings` (published only, paginated, `?market=`) and `GET /api/listings/{id}` are guarded by `listing.read` (members and above; anonymous receives the generic 401 and the frontend shows the sign-in gate, as the identity design intends). Map pins use the listing's geocoded point because seeds set `location_disclosed=true`; sellers' listings in Wave 2b default to false (Census plan D8).
- **D9 — Quality.** Test-first everything: schema contract test, geocode bounds test, photo pipeline test (dimensions, size, count, inventory hashes), seed idempotency test on a scratch database, endpoint tests (401 anonymous, 200 member, unpublished hidden, pagination), frontend tests (listings replace `P` keeping field names; the design-fixture stub for the gates), perf budgets for `/api/listings` in `tests/perf/test_api_latency.py`, 100 % lines and branches backend and frontend, zero-regression on the fourteen unchanged screens.

### The programme's standing rules

- **(a) 100 % lines AND branches, backend.** Every task's local gate is `poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100`. `scripts/` is in the coverage scope for this plan because two of its four deliverables live there. **→ John (pre-flight I6):** `--cov=scripts` is a *new* scope — `main`'s CI runs `--cov=app … --cov-fail-under=90` and Wave 2a's runs `--cov=app --cov-branch --cov-fail-under=100`; neither includes `scripts/`, so `coverage.xml` carries no `scripts/*.py` rows and `diff-cover … --fail-under=100` cannot enforce the two new modules. The default applied here is to **add `--cov=scripts` to `.github/workflows/quality.yml` in Task L5**, so the gate that holds locally also holds on every PR. The Preconditions establish the baseline first: if `scripts/migrate.py` is not already at 100 % lines and branches, Task L1's own gate would fail before this plan has written a line — that is a STOP, not something to work around.
- **(b) 100 % lines, branches, functions and statements, frontend.** `cd frontend && npx vitest run --coverage`. The documented `coverage.exclude` list in `frontend/vite.config.ts` is **not widened** by this plan; the new module `frontend/src/listings/load.ts` is covered at 100 %.
- **(c) No suppressions.** No `# pragma: no cover`, no `# noqa`, no `# type: ignore`, no `@ts-expect-error`, no `@ts-nocheck`, no `assert` used as control flow in production code. A cast at a typed boundary (`x as unknown as T`) is not a suppression and is allowed where it is documented; a suppression comment is not.
- **(d) `poetry run mypy app --strict`** — 0 errors. **`poetry run ruff check app tests scripts`** — 0 findings, on ruff's default rule set plus `extend-select = ["I", "RUF"]`, with **no ignores added**.
- **(e) Every route is guarded or in `PUBLIC_ROUTES`.** `tests/auth/test_permissions.py::test_every_route_is_guarded_or_public` walks `create_app()`. This plan adds three guarded routes and **adds nothing to `PUBLIC_ROUTES`**.
- **(f) `audit.write(` is called directly in audited endpoints.** `listing.read` is not in `permissions.AUDITED`, so no endpoint in this plan writes an audit row; `test_audited_permissions_are_written_by_their_handlers` proves that stays true rather than being assumed.
- **(g) `require(...)` is hoisted to a module-level constant** and never wrapped. A fresh `require(...)` per route still resolves, but a wrapper does not — `app.auth.deps.permission_of` is keyed by object identity, and `_unresolvable()` fails the build on an unreadable guard.
- **(h) No Google content is stored.** Geocoding is the U.S. Census Bureau Geocoder only (public domain, no key). No Google Places `place_id`, no Google Geocoding result, no Google imagery reaches the database, the seed files or the repository.
- **(i) Secrets never in git.** No new secret is introduced by this plan. `gitleaks detect` must stay at 0 findings.
- **(j) QA only.** `scripts/deploy.sh QA` then `scripts/verify-deploy.sh QA`. **Production stays in `coming_soon` mode and is never deployed or seeded by this sub-project** (D7: "never on production without John's go"). Before any Railway action run `railway status` and read back **Project: Practice Match**.
- **(k) Conventional commits, explicit pathspecs, both remotes.** Every commit names its files (`git add <path> …`), never `git add -A` or `git add .`. Every commit message carries the trailer:

  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  ```

  Push to both `origin` (vin-swe/practice-match) and `production` (johndean/practice-match) when the branch is handed back.
- **(l) Deviations STOP.** Any divergence from this plan or the spec — a geocode that lands outside its bounds, a photograph folder that does not match its slug, a design field the V3 port does not read — **stops work and is reported to John**. Do not improvise a substitute, do not widen a tolerance, do not relax a bound.
- **(m) Surgical diffs.** The change contains the ask and nothing else. No drive-by refactors, no reformatting, no removal of a function or feature while doing unrelated work.
- **(n) Zero pixel tolerance, never relaxed.** `frontend/tests/playwright.config.ts` stays at `maxDiffPixels: 0`. A visual failure is this plan leaking into the design's pixels — stop and diff.

---

## Preconditions

This plan does not start until **both** of the following are on `main`. Verify each by grep, not by memory; if any check fails, **STOP** — the branch is not ready.

**From Wave 2a Task I4 (`feat/identity`):**

```bash
cd "/Users/johndean/Development/Practice Match"
grep -n "^def require(perm: str)" app/auth/deps.py                    # the guard factory
grep -n "^def install(app: FastAPI) -> None:" app/auth/deps.py        # the AuthError handler installer
grep -n "class AuthError" app/auth/deps.py                            # decision A5's body
grep -n '"listing.read"' app/auth/permissions.py                      # the permission this plan consumes
grep -n "PUBLIC_ROUTES" app/auth/permissions.py
grep -n "def test_every_route_is_guarded_or_public" tests/auth/test_permissions.py
grep -n "def write(" app/auth/audit.py
grep -n "^def hit(" app/auth/limits.py
grep -n "def sync_conn" app/db.py                                     # psycopg2 connection factory
grep -n "def sync_redis" app/cache.py                                 # one client per process
grep -n "^def member" -n tests/api/conftest.py || grep -n "def member" tests/api/conftest.py
grep -n "def conn\|def redis\|def scratch_dsn" tests/conftest.py
ls migrations/01[0-4]_*.sql                                           # 010–014 exist; this plan starts at 015
```

Expected: every grep hits. `app.auth.deps.require` returns `Callable[[Request], S.Principal | None]` and raises `KeyError` at wiring time for an unknown permission; `install(app)` is already called from `app.main.create_app()`; `tests/api/conftest.py` provides `client` (base URL `https://qa.foundation.vin`) and `member(roles=("buyer",), state="active", email=None, affiliation=None) -> (account_id, cookies, headers)`; `tests/conftest.py` provides `conn` (a scratch database with every migration applied, `settings.database_url` monkeypatched to it), `redis` (fakeredis, patched into `app.cache`) and `scratch_dsn`.

**From Browse V3:**

```bash
ls frontend/src/components/MarketMapView.vue
grep -n "browse-market-panel\|'browse'" frontend/tests/screens.ts     # the V3 state list
grep -c "name: '" frontend/tests/screens.ts                           # expect 27
grep -n "design_handoff_practice_match_v3" frontend/tests/app-generated.test.ts
ls frontend/tests/baseline-manifest.json                              # the thirteen frozen hashes
```

Expected: `MarketMapView.vue` exists in its V3 shape (mosaic shading, `rf-tip`, persistent `rf-callout`, `onBasemap`-gated tabs); `frontend/tests/screens.ts` carries the 27 V3 states including `browse`, `browse-market-panel`, `mobile-map`, `detail`; `frontend/src/logic.js` is the V3 port and ends with `export { Component };`.

**Environment:**

```bash
docker compose -f docker-compose.dev.yml up -d
cd frontend && npm ci && npm run build && cd ..
poetry install
```

**Coverage baseline (do this before Task L1, on the untouched branch):**

```bash
cd "/Users/johndean/Development/Practice Match"
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
```

Expected: PASS. This plan's per-task gate adds `--cov=scripts` to the scope Wave 2a's CI already runs, and `scripts/` has never been under a coverage gate (pre-flight I6). If this fails on the untouched branch — most likely on `scripts/migrate.py`'s error arms — **STOP and report to John**: Task L1 Step 5 would otherwise fail for a reason that has nothing to do with this plan, and lowering the threshold is not an option (Global Constraint (a)). Record the pass, with its reported `scripts/` percentages, in the hand-back note.

---

## File Structure

| File | Kind | Responsibility | Task |
|---|---|---|---|
| `migrations/015_listing.sql` | migration (new) | the `listing` table, its checks, its GiST and pagination indexes | L1 |
| `tests/test_listing_schema.py` | test (new) | schema contract: columns, types, checks, indexes, SRID | L1 |
| `seeds/hospitals.json` | data (new) | John's eighteen rows verbatim + derived + demo + geocoded | L2 |
| `tests/seeds/test_hospitals_json.py` | test (new) | JSON schema, D4 type derivation, slug/folder agreement | L2 |
| `tests/seeds/test_geocode_bounds.py` | test (new) | state bbox + ≤ 25 km from city centroid, tables committed in the test | L2 |
| `scripts/prepare_photos.py` | script (new) | curated folders → WebP ≤ 1600 px / ≤ 250 KB, metadata stripped, inventory | L3 |
| `seeds/hospitals/photos/<slug>/1..4.webp` | data (new, committed) | the served photographs | L3 |
| `seeds/hospitals/photos/index.json` | data (new, committed) | inventory with SHA-256s | L3 |
| `tests/scripts/test_prepare_photos.py` | test (new) | pipeline on a temp folder of generated images | L3 |
| `tests/seeds/test_photo_inventory.py` | test (new) | the committed outputs match the inventory and the size ceiling | L3 |
| `scripts/seed_listings.py` | script (new) | idempotent upsert by `slug`; `--reset`; exit codes | L4 |
| `scripts/start.sh` | script (modified) | the `seed` role | L4 |
| `tests/scripts/test_seed_listings.py` | test (new) | idempotency, `--reset`, count 18, exit codes, on a scratch DB | L4 |
| `tests/scripts/test_start_sh.sh` | test (modified) | the `seed` role dispatches | L4 |
| `Dockerfile` | build (modified) | `COPY seeds/ ./seeds/` — the seed data and photos ship in the image | L4 |
| `tests/test_build_config.py` | test (modified) | the Dockerfile carries the seeds COPY | L4 |
| `DEPLOY.md` | docs (modified) | how to seed QA in-container | L4 |
| `app/api/listings.py` | API (new) | the three `listing.read` endpoints, Redis-cached list, A5 bodies | L5 |
| `app/main.py` | API (modified) | include the listings router before the catch-all | L5 |
| `tests/api/test_listings.py` | test (new) | 401/200, unpublished hidden, pagination, photo 404, undisclosed location | L5 |
| `tests/perf/conftest.py` | test (new) | re-export `member` for the perf suite without shadowing root `client` | L5 |
| `tests/perf/test_api_latency.py` | test (modified) | the listings budgets | L5 |
| `frontend/src/listings/load.ts` | hand-written (new) | fetch `/api/listings`, map to the design's field names, replace `P`/`MARKETS` in place | L6 |
| `frontend/src/listings/load.test.ts` | test (new) | 100 % of the new module, round-trip identity against the design's fixtures | L6 |
| `frontend/src/logic.js` | ported (footer edit) | `export { Component, MARKETS, P };` | L6 |
| `frontend/tests/app-generated.test.ts` | gate (modified) | the port drift test's `FOOTER` constant | L6 |
| `frontend/src/main.ts` | hand-written (modified) | load before bootstrap | L6 |
| `frontend/src/main.test.ts` | test (modified) | fetch stubbed; the fixtures survive a refusal | L6 |
| `frontend/tests/design-listings.mjs` | test double (new) | the design's own fixtures in API shape, derived from `P` | L6 |
| `frontend/tests/harness.ts` | gate (modified) | `prepare()` serves the stub to the app project | L6 |
| `tests/scripts/__init__.py` | test package marker (new) | keeps `tests/scripts/*.py` importable from the repo root | L3 |
| `scripts/verify-image.sh` + `tests/scripts/test_verify_image_sh.sh` | ops (modified) | prove `seeds/` really is inside the built image | L4 |
| `.github/workflows/quality.yml` | CI (modified) | `--cov=scripts` so the two new scripts are enforced on every PR | L5 |
| `pyproject.toml`, `frontend/package.json` | tooling | Pillow (dev group); the lockstep version bump | L3, L7 |

---

### Task L1: The `listing` table

**Files:**
- Create: `migrations/015_listing.sql`
- Create: `tests/test_listing_schema.py`
- Unchanged: `scripts/migrate.py` (the ledger runner already applies `[0-9][0-9][0-9]_*.sql` in name order; nothing about this file needs new runner behaviour — it is a single transactional `CREATE TABLE` + `CREATE INDEX`, no `CREATE INDEX CONCURRENTLY`)

**Interfaces:**
- Consumes: `migrations/001_init.sql`'s `CREATE EXTENSION postgis` (for `geography`), `gen_random_uuid()` (built in from PostgreSQL 13; both Railway databases are pinned to `postgis/postgis:16-3.5`), and `tests/conftest.py`'s `conn` fixture.
- Produces: table `listing` with columns `id uuid`, `slug text UNIQUE`, `name text`, `street text`, `city text`, `state text`, `zip text`, `phone text`, `hours text`, `status text` (checked), `location_disclosed boolean`, `geom geography(Point,4326)`, `area text`, `type text` (checked), `price bigint`, `rev bigint`, `docs int`, `rooms int`, `sqft int`, `bldg text` (checked), `est int`, `listed_at timestamptz`, `note text`, `staff text`, `services text`, `facility text`, `ownership text`, `market text`, `photos jsonb`, `source text` (checked), `created_at timestamptz`, `updated_at timestamptz`; indexes `listing_geom_gix` (GiST on `geom`) and `listing_page_idx`. Tasks L4 and L5 write and read exactly these names.

> **Why `geography`, not `geometry`.** Distance and containment on a `geography(Point,4326)` are computed on the spheroid in metres, which is what "within 25 km of the city centroid" and Wave 2b's radius search both mean. A GiST index on a geography column is what makes `ST_DWithin` an index scan rather than a sequential one. The Census plan's Phase B joins against this column, so the type is part of the contract, not a preference.

> **`pop` / `growth` / `income` / `hh` are deliberately absent** from this table. D4 leaves the community figures null until the Census plan supplies them, and the Census plan's Phase B stores them in its own `market_metric` table keyed by `listing_id` — putting nullable copies here would create two homes for one fact. The API returns them as `null` (Task L5) and the UI shows its existing empty state.

- [ ] **Step 1: Write the failing schema-contract test**

Create `tests/test_listing_schema.py`:

```python
"""Schema contract for migrations/015_listing.sql (spec 2026-09-06 D1).

Every column name here is read by scripts/seed_listings.py (L4) and app/api/listings.py
(L5), and by Wave 2b and the Census plan's Phase B after them. A rename that does not
also change this file is a break, not a refactor.
"""
from typing import Any

EXPECTED_COLUMNS: dict[str, tuple[str, bool]] = {
    # name: (data_type, is_nullable)
    "id": ("uuid", False),
    "slug": ("text", False),
    "name": ("text", False),
    "street": ("text", True),
    "city": ("text", False),
    "state": ("text", False),
    "zip": ("text", True),
    "phone": ("text", True),
    "hours": ("text", True),
    "status": ("text", False),
    "location_disclosed": ("boolean", False),
    "geom": ("USER-DEFINED", True),
    "area": ("text", False),
    "type": ("text", False),
    "market": ("text", False),
    "price": ("bigint", True),
    "rev": ("bigint", True),
    "docs": ("integer", True),
    "rooms": ("integer", True),
    "sqft": ("integer", True),
    "bldg": ("text", True),
    "est": ("integer", True),
    "listed_at": ("timestamp with time zone", False),
    "note": ("text", True),
    "staff": ("text", True),
    "services": ("text", True),
    "facility": ("text", True),
    "ownership": ("text", True),
    "photos": ("jsonb", False),
    "source": ("text", False),
    "created_at": ("timestamp with time zone", False),
    "updated_at": ("timestamp with time zone", False),
}


def _rows(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def test_listing_has_exactly_the_contracted_columns(conn: Any) -> None:
    found = {
        name: (dtype, nullable == "YES")
        for name, dtype, nullable in _rows(
            conn,
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'listing'",
        )
    }
    assert found == EXPECTED_COLUMNS


def test_geom_is_a_geography_point_in_4326(conn: Any) -> None:
    rows = _rows(
        conn,
        "SELECT type, srid FROM geography_columns WHERE f_table_name = 'listing' AND f_geography_column = 'geom'",
    )
    assert rows == [("Point", 4326)]


def test_geom_has_a_gist_index(conn: Any) -> None:
    defs = [d for (d,) in _rows(conn, "SELECT indexdef FROM pg_indexes WHERE tablename = 'listing'")]
    assert any("USING gist" in d and "(geom)" in d for d in defs), defs


def test_the_pagination_key_is_indexed(conn: Any) -> None:
    """L5 pages published listings on (listed_at DESC, id DESC), filtered by status and market."""
    defs = [d for (d,) in _rows(conn, "SELECT indexdef FROM pg_indexes WHERE tablename = 'listing'")]
    assert any("listing_page_idx" in d for d in defs), defs


def test_slug_is_unique(conn: Any) -> None:
    import psycopg2
    import pytest

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source)"
            " VALUES ('dup','A','X','TX','X','Small animal','X, TX','seed')"
        )
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO listing (slug, name, city, state, area, type, market, source)"
                " VALUES ('dup','B','Y','TX','Y','Small animal','Y, TX','seed')"
            )


def test_status_source_type_and_bldg_are_checked(conn: Any) -> None:
    import psycopg2
    import pytest

    base = (
        "INSERT INTO listing (slug, name, city, state, area, type, market, source, status, bldg)"
        " VALUES (%s,'A','X','TX','X',%s,'X, TX',%s,%s,%s)"
    )
    bad = [
        ("s1", "Small animal", "seed", "live", "Included"),          # unknown status
        ("s2", "Small animal", "scraped", "published", "Included"),  # unknown source
        ("s3", "Aquatic", "seed", "published", "Included"),          # unknown type
        ("s4", "Small animal", "seed", "published", "Rented"),       # unknown bldg
    ]
    for params in bad:
        with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(base, params)


def test_defaults_are_what_the_seeder_relies_on(conn: Any) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source)"
            " VALUES ('defaults','A','X','TX','X','Small animal','X, TX','seed')"
            " RETURNING id IS NOT NULL, status, location_disclosed, photos, listed_at IS NOT NULL,"
            " created_at IS NOT NULL, updated_at IS NOT NULL"
        )
        assert cur.fetchone() == (True, "draft", False, [], True, True, True)
```

> **Why `pytest.raises` and not `try/except/else`.** A `try/except Exception … else: raise AssertionError(...)` has an arm that is never taken on a correct schema, which is a branch `--cov-branch` will report as uncovered and which Global Constraint (c) forbids papering over with `# pragma: no cover`. `pytest.raises(psycopg2.errors.CheckViolation)` has no such arm and names the exact error, so a *different* failure (a typo in the SQL, say) is a test failure rather than a false pass. The two `import` statements sit inside the test bodies only so this snippet is copy-pasteable; move them to the top of the file when you write it, or ruff's isort rule will move them for you.

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/test_listing_schema.py -v`
Expected: every test FAILS — `psycopg2.errors.UndefinedTable: relation "listing" does not exist` (the `conn` fixture builds a scratch database from `migrations/`, which has no `015` yet).

- [ ] **Step 3: Write the migration**

Create `migrations/015_listing.sql`:

```sql
-- Seed Listings (spec 2026-09-06, D1). The marketplace's listing table: the eighteen seeded
-- demo hospitals today (source='seed'), sellers' own listings in Wave 2b (source='seller'),
-- and the row the Census plan's Phase B joins its market metrics to.
--
-- geography(Point,4326), not geometry: distance and containment are computed on the spheroid
-- in metres, which is what the geocode bounds test and Wave 2b's radius search both mean.
-- The community figures (pop/growth/income/hh) deliberately live in the Census plan's own
-- table, not here (D4) — nullable copies would give one fact two homes.
CREATE TABLE listing (
  id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  slug               text        NOT NULL UNIQUE,
  name               text        NOT NULL,
  street             text,
  city               text        NOT NULL,
  state              text        NOT NULL,
  zip                text,
  phone              text,
  hours              text,
  status             text        NOT NULL DEFAULT 'draft'
                                 CHECK (status IN ('draft','in_review','published','paused','withdrawn')),
  -- false hides street/zip and the geocoded point from every reader (L5). Seeds set true (D8);
  -- sellers' listings in Wave 2b default to false, which is why the default here is false.
  location_disclosed boolean     NOT NULL DEFAULT false,
  geom               geography(Point,4326),
  area               text        NOT NULL,
  type               text        NOT NULL
                                 CHECK (type IN ('Small animal','Mixed','Large animal','Emergency','Specialty')),
  market             text        NOT NULL,
  price              bigint,
  rev                bigint,
  docs               integer,
  rooms              integer,
  sqft               integer,
  bldg               text        CHECK (bldg IN ('Included','Leased','Separate')),
  est                integer,
  listed_at          timestamptz NOT NULL DEFAULT now(),
  note               text,
  staff              text,
  services           text,
  facility           text,
  ownership          text,
  -- Relative paths under seeds/hospitals/photos/, e.g. ["6666_dallas.../1.webp", …]. The API
  -- resolves them under that root and refuses anything that escapes it (L5).
  photos             jsonb       NOT NULL DEFAULT '[]'::jsonb,
  source             text        NOT NULL CHECK (source IN ('seed','seller')),
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX listing_geom_gix  ON listing USING gist (geom);
-- The exact key L5 pages on: published rows, optionally one market, newest first, id as the
-- tie-break so a cursor is total.
CREATE INDEX listing_page_idx  ON listing (status, market, listed_at DESC, id DESC);
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `poetry run pytest tests/test_listing_schema.py -v`
Expected: PASS — seven tests.

Then prove the runner is genuinely unchanged and the file applies through it:

```bash
git diff --stat scripts/migrate.py     # expect: no output
poetry run pytest tests/test_migrate.py -q
```
Expected: empty diff; `tests/test_migrate.py` green.

- [ ] **Step 5: Run the full backend gate**

```bash
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
```
Expected: 0 findings, 0 errors, all green at 100 %.

- [ ] **Step 6: Commit**

```bash
cd "/Users/johndean/Development/Practice Match"
git add migrations/015_listing.sql tests/test_listing_schema.py
git commit -m "feat(db): listing table — geography point, status/source/type checks, photos jsonb

Spec 2026-09-06 D1. Migrations start at 015 (identity holds 010-014). geom is
geography(Point,4326) with a GiST index so Wave 2b's radius search and the geocode
bounds test both measure metres on the spheroid; listing_page_idx is the exact key
GET /api/listings pages on. The community figures stay with the Census plan.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task L2: `seeds/hospitals.json` — John's eighteen rows, geocoded

**Files:**
- Create: `seeds/hospitals.json`
- Create: `tests/seeds/__init__.py`
- Create: `tests/seeds/test_hospitals_json.py`
- Create: `tests/seeds/test_geocode_bounds.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (this is data plus its tests).
- Produces: `seeds/hospitals.json` — a JSON object `{"version": 1, "note": "...", "hospitals": [ … 18 objects … ]}`. Each hospital object carries: `slug`, `name`, `street`, `city`, `state`, `zip`, `phone`, `hours`, `area`, `market`, `type`, `status`, `source`, `location_disclosed`, `lat`, `lng`, `geocode: {tier, matched_address, benchmark}`, `demo` (always `true`), `price`, `rev`, `docs`, `rooms`, `sqft`, `bldg`, `est`, `listed_days_ago`, `note`, `staff`, `services`, `facility`, `ownership`. Task L3 reads `slug`; Task L4 reads every field.

> **`listed_days_ago`, not a date.** A committed absolute date would make the seeds read "18 months ago" a year from now. The seeder computes `listed_at = now() - (listed_days_ago || ' days')::interval` at seed time, and the API renders the design's relative string from it (Task L5). The number is the fixture; the date is derived.

> **`area` and `market` are derived, not invented.** `area` is the city from John's table (the design's cards show area + type, D5); `market` is `"<City>, <ST>"`. That yields eleven markets — Dallas TX, New York NY, Denver CO, Santa Barbara CA, Houston TX, Los Angeles CA, South Lake Tahoe CA, Sacramento CA, Orlando FL, Atlanta GA, Austin TX — which is what the metro selector will list on QA.

> **`slug` is the photograph folder name.** The eighteen curated folders are named `<slug>_individual_images`. Making `slug` exactly that prefix is what lets `scripts/prepare_photos.py` (L3) map folder → hospital with no lookup table, and the test in Step 1 pins it. Note `jkl_animal_hospital` — the folder does **not** spell out "critical care"; the slug follows the folder, the `name` follows John's table.

### The geocode step — run once, by hand, before writing the file

The U.S. Census Bureau Geocoder is public domain and needs no key. **Nothing in the test suite ever calls it**; this runs once and its output is committed.

```bash
cd "/Users/johndean/Development/Practice Match"
cat > /tmp/pm-addresses.txt <<'ADDR'
6666_dallas_veterinary_specialist_hospital|17727 Dallas Pkwy, Suite 150, Dallas, TX 75287
5555_new_york_veterinary_specialist_hospital|510 E 62nd St, New York, NY 10065
4444_denver_veterinary_specialist_hospital|9770 E Alameda Ave, Denver, CO 80247
3333_santa_barbara_veterinary_specialist_hospital|414 E Carrillo St, Santa Barbara, CA 93101
2222_pet_hospital|8042 Katy Freeway, Houston, TX 77024
1111_pet_hospital|6565 Santa Monica Blvd, Los Angeles, CA 90038
789_lake_tahoe_pet_hospital|921 Emerald Bay Rd, South Lake Tahoe, CA 96150
456_pet_er|2500 N San Fernando Rd, Los Angeles, CA 90065
123_route66|4641 Colorado Blvd, Los Angeles, CA 90039
yz_rural_animal_hospital|8299 E Stockton Blvd, Sacramento, CA 95828
vwx_veterinary_hospital|11011 Lake Underhill Rd, Orlando, FL 32825
stu_veterinary_specialist_center|2080 Principal Row, Orlando, FL 32837
pqr_veterinary_hospital|9801 Old Winery Place, Sacramento, CA 95827
mno_pet_hospital|1917 P Street, Sacramento, CA 95811
jkl_animal_hospital|1700 Century Cir NE, Atlanta, GA 30345
ghi_veterinary_hospital|7501 N Capital of Texas Hwy, Building A, Austin, TX 78731
def_veterinary_hospital|4434 Frontier Trail, Austin, TX 78745
abc_animal_hospital|6730 Airline Dr, Houston, TX 77076
ADDR

while IFS='|' read -r slug addr; do
  python3 - "$slug" "$addr" <<'PY'
import json, sys, urllib.parse, urllib.request
slug, addr = sys.argv[1], sys.argv[2]
url = ("https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
       f"?address={urllib.parse.quote(addr)}&benchmark=Public_AR_Current&format=json")
with urllib.request.urlopen(url, timeout=30) as fh:
    matches = json.load(fh)["result"]["addressMatches"]
if not matches:
    print(json.dumps({"slug": slug, "ERROR": "no match", "address": addr}))
    sys.exit(0)
m = matches[0]
print(json.dumps({
    "slug": slug,
    "lat": round(m["coordinates"]["y"], 6),
    "lng": round(m["coordinates"]["x"], 6),
    "geocode": {"tier": m["tigerLine"]["side"] and m.get("addressComponents", {}).get("preType", "") or "",
                "matched_address": m["matchedAddress"], "benchmark": "Public_AR_Current"},
}))
PY
  sleep 1
done < /tmp/pm-addresses.txt
```

Record the **match tier** as the geocoder reports it. The `locations/onelineaddress` endpoint returns one `addressMatches` entry per candidate; the tier this plan records is the string `"exact"` when `matchedAddress` resolves to the same house number and street as the input, and `"approximate"` when it resolves to a range interpolation or a different house number. Decide per row by reading `matchedAddress` against the input, and write the value you decided — do not fabricate a field the API did not return. If a row returns **no match**, or a `matchedAddress` in a different city or state, **STOP and report it to John** (Global Constraint (l)); do not substitute a hand-picked coordinate.

The Dallas row is the verification anchor and has already been probed: `17727 Dallas Pkwy, Suite 150, Dallas, TX 75287` resolves to `(-96.829738, 32.991596)` — that is `lng = -96.829738`, `lat = 32.991596`.

**If your run returns a different Dallas coordinate** (`Public_AR_Current` is a rolling benchmark, so this is possible without anything being wrong): it is acceptable **only if** the new point still passes the bounding-box and 25 km tests in Step 5. In that case update `DALLAS_ANCHOR` in `tests/seeds/test_geocode_bounds.py` in the same commit and record the change in the L7 hand-back note. If it fails either bound, **STOP and report to John** — that is a bad match, not a stale constant. The committed value has only 0.91 km of headroom (24.09 km against the 25 km limit), so this row is the plan's most fragile data dependency and deserves the extra look.

- [ ] **Step 1: Write the failing JSON-shape and derivation test**

Create `tests/seeds/__init__.py` (empty) and `tests/seeds/test_hospitals_json.py`:

```python
"""seeds/hospitals.json is John's table of 2026-09-06, verbatim (spec §2), plus the fields
the design needs that his table does not carry (D4) and the coordinates the implementer
geocoded once (D2). This file is the contract every later task reads."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SEEDS = ROOT / "seeds" / "hospitals.json"
PHOTO_SOURCE_SUFFIX = "_individual_images"

# John's table, verbatim: (name, city, state, street, zip, phone, hours).
JOHNS_TABLE: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    ("6666 Dallas Veterinary Specialist Hospital", "Dallas", "TX", "17727 Dallas Pkwy, Suite 150", "75287", "(214) 555-0101", "Mon–Fri 8 AM–5 PM"),
    ("5555 New York Veterinary Specialist Hospital", "New York", "NY", "510 E 62nd St", "10065", "(212) 555-0102", "24/7"),
    ("4444 Denver Veterinary Specialist Hospital", "Denver", "CO", "9770 E Alameda Ave", "80247", "(303) 555-0103", "24/7"),
    ("3333 Santa Barbara Veterinary Specialist Hospital", "Santa Barbara", "CA", "414 E Carrillo St", "93101", "(805) 555-0104", "24/7"),
    ("2222 Pet Hospital", "Houston", "TX", "8042 Katy Freeway", "77024", "(713) 555-0105", "24/7 emergency"),
    ("1111 Pet Hospital", "Los Angeles", "CA", "6565 Santa Monica Blvd", "90038", "(323) 555-0106", "24/7"),
    ("789 Lake Tahoe Pet Hospital", "South Lake Tahoe", "CA", "921 Emerald Bay Rd", "96150", "(530) 555-0107", "Mon–Sat 8 AM–6 PM"),
    ("456 Pet ER Hospital", "Los Angeles", "CA", "2500 N San Fernando Rd", "90065", "(323) 555-0108", "24/7"),
    ("123 Route 66 Animal Hospital", "Los Angeles", "CA", "4641 Colorado Blvd", "90039", "(818) 555-0109", "24/7"),
    ("YZ Rural Animal Hospital", "Sacramento", "CA", "8299 E Stockton Blvd", "95828", "(916) 555-0110", "24/7"),
    ("VWX Veterinary Hospital", "Orlando", "FL", "11011 Lake Underhill Rd", "32825", "(407) 555-0111", "24/7"),
    ("STU Veterinary Specialist Center", "Orlando", "FL", "2080 Principal Row", "32837", "(407) 555-0112", "Mon–Thu 8 AM–6 PM"),
    ("PQR Veterinary Hospital", "Sacramento", "CA", "9801 Old Winery Place", "95827", "(916) 555-0113", "6 AM–12 AM"),
    ("MNO Pet Hospital", "Sacramento", "CA", "1917 P Street", "95811", "(916) 555-0114", "Mon–Fri 8 AM–6 PM; Sat 9 AM–5 PM"),
    ("JKL Animal Critical Care & ER Hospital", "Atlanta", "GA", "1700 Century Cir NE", "30345", "(404) 555-0115", "24/7"),
    ("GHI Veterinary Hospital", "Austin", "TX", "7501 N Capital of Texas Hwy, Building A", "78731", "(512) 555-0116", "24/7 emergency"),
    ("DEF Veterinary Hospital", "Austin", "TX", "4434 Frontier Trail", "78745", "(512) 555-0117", "24/7"),
    ("ABC Animal Hospital", "Houston", "TX", "6730 Airline Dr", "77076", "(713) 555-0118", "Mon/Tue/Thu/Fri 7:30 AM–6 PM; Sat 7:30 AM–5 PM"),
)

REQUIRED_KEYS = {
    "slug", "name", "street", "city", "state", "zip", "phone", "hours", "area", "market", "type",
    "status", "source", "location_disclosed", "lat", "lng", "geocode", "demo",
    "price", "rev", "docs", "rooms", "sqft", "bldg", "est", "listed_days_ago",
    "note", "staff", "services", "facility", "ownership",
}


def load() -> list[dict[str, object]]:
    data = json.loads(SEEDS.read_text(encoding="utf-8"))
    assert data["version"] == 1
    hospitals = data["hospitals"]
    assert isinstance(hospitals, list)
    return hospitals


def derived_type(name: str, hours: str) -> str:
    """D4, in the order D4 states it: Specialist wins over emergency hours."""
    if "Specialist" in name:
        return "Specialty"
    if "ER" in name.split() or "Critical Care" in name or "24/7 emergency" in hours:
        return "Emergency"
    return "Small animal"


def test_there_are_exactly_eighteen_hospitals() -> None:
    assert len(load()) == 18


def test_johns_table_is_reproduced_verbatim_and_in_order() -> None:
    rows = load()
    got = tuple((h["name"], h["city"], h["state"], h["street"], h["zip"], h["phone"], h["hours"]) for h in rows)
    assert got == JOHNS_TABLE


def test_every_hospital_carries_every_contracted_key() -> None:
    for h in load():
        assert set(h) == REQUIRED_KEYS, (h["slug"], set(h) ^ REQUIRED_KEYS)


def test_type_is_derived_exactly_as_d4_says() -> None:
    for h in load():
        assert h["type"] == derived_type(str(h["name"]), str(h["hours"])), h["slug"]


def test_the_derivation_produces_five_specialty_four_emergency_and_nine_small_animal() -> None:
    counts: dict[str, int] = {}
    for h in load():
        counts[str(h["type"])] = counts.get(str(h["type"]), 0) + 1
    assert counts == {"Specialty": 5, "Emergency": 4, "Small animal": 9}


def test_every_phone_is_a_555_number() -> None:
    for h in load():
        assert " 555-" in str(h["phone"]), h["slug"]


def test_area_and_market_are_derived_from_the_city_and_state() -> None:
    for h in load():
        assert h["area"] == h["city"], h["slug"]
        assert h["market"] == f"{h['city']}, {h['state']}", h["slug"]


def test_every_row_is_a_published_disclosed_demo_seed() -> None:
    for h in load():
        assert h["status"] == "published" and h["source"] == "seed", h["slug"]
        assert h["location_disclosed"] is True and h["demo"] is True, h["slug"]
        assert h["note"] == "Demo listing seeded by the VIN Foundation.", h["slug"]


def test_the_demo_business_fields_are_present_and_plausible() -> None:
    for h in load():
        assert isinstance(h["price"], int) and 500_000 <= int(h["price"]) <= 4_000_000, h["slug"]
        assert isinstance(h["rev"], int) and int(h["rev"]) > int(h["price"]) * 0.5, h["slug"]
        assert 1 <= int(h["docs"]) <= 12 and 1 <= int(h["rooms"]) <= 12, h["slug"]
        assert 2_000 <= int(h["sqft"]) <= 12_000, h["slug"]
        assert h["bldg"] in ("Included", "Leased", "Separate"), h["slug"]
        assert 1900 <= int(h["est"]) <= 2026, h["slug"]
        assert 0 <= int(h["listed_days_ago"]) <= 60, h["slug"]
        for text_field in ("staff", "services", "facility", "ownership"):
            assert isinstance(h[text_field], str) and h[text_field], (h["slug"], text_field)


# The eighteen curated photograph folders are named `<slug>_individual_images`. Pinning the
# set here is what lets scripts/prepare_photos.py map folder -> hospital with no lookup table,
# and what catches a slug being "tidied up" without its folder.
PHOTO_FOLDER_SLUGS = frozenset({
    "6666_dallas_veterinary_specialist_hospital", "5555_new_york_veterinary_specialist_hospital",
    "4444_denver_veterinary_specialist_hospital", "3333_santa_barbara_veterinary_specialist_hospital",
    "2222_pet_hospital", "1111_pet_hospital", "789_lake_tahoe_pet_hospital", "456_pet_er",
    "123_route66", "yz_rural_animal_hospital", "vwx_veterinary_hospital",
    "stu_veterinary_specialist_center", "pqr_veterinary_hospital", "mno_pet_hospital",
    "jkl_animal_hospital", "ghi_veterinary_hospital", "def_veterinary_hospital",
    "abc_animal_hospital",
})
PHOTO_FOLDER_NAMES = frozenset(slug + PHOTO_SOURCE_SUFFIX for slug in PHOTO_FOLDER_SLUGS)


def test_slugs_are_unique_and_name_the_photograph_folders() -> None:
    slugs = [str(h["slug"]) for h in load()]
    assert len(set(slugs)) == 18
    assert set(slugs) == PHOTO_FOLDER_SLUGS
    for slug in slugs:
        assert slug == slug.lower() and " " not in slug, slug
        # The folder scripts/prepare_photos.py will actually open, pinned as a set rather than
        # re-derived — a concatenation of two non-empty strings is always truthy and proves
        # nothing (pre-flight M1).
        assert (slug + PHOTO_SOURCE_SUFFIX) in PHOTO_FOLDER_NAMES, slug


def test_the_geocode_provenance_is_recorded() -> None:
    for h in load():
        geo = h["geocode"]
        assert isinstance(geo, dict)
        assert geo["benchmark"] == "Public_AR_Current", h["slug"]
        assert geo["tier"] in ("exact", "approximate"), (h["slug"], geo["tier"])
        assert isinstance(geo["matched_address"], str) and geo["matched_address"], h["slug"]


def _spec_table_rows() -> list[tuple[str, str, str, str, str]]:
    """§2 of the spec, parsed out of its markdown table: (name, city/state, address, phone, hours).

    Pre-flight I12: `JOHNS_TABLE` above is a hand-typed SECOND copy of John's table, so a typo
    made in both copies passes silently. John's standing rule is a drift test wherever a
    document and code can diverge — this is that test's data source, read from the spec itself."""
    spec = (ROOT / "docs" / "superpowers" / "specs" / "2026-09-06-seed-listings-design.md")
    rows: list[tuple[str, str, str, str, str]] = []
    for line in spec.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| ---") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[0] in ("Seed hospital", "") or set(cells[0]) <= set("-: "):
            continue
        rows.append((cells[0], cells[1], cells[2], cells[3], cells[4]))
    return rows


def test_the_spec_table_parses_to_exactly_eighteen_rows() -> None:
    assert len(_spec_table_rows()) == 18, "the §2 table parser no longer matches the spec's markdown"


def test_the_seed_file_reconstructs_the_spec_table_exactly() -> None:
    """Every row of §2, rebuilt from seeds/hospitals.json and compared to the spec verbatim."""
    rebuilt = [
        (
            str(h["name"]),
            f"{h['city']}, {h['state']}",
            f"{h['street']}, {h['city']}, {h['state']} {h['zip']}",
            str(h["phone"]),
            str(h["hours"]),
        )
        for h in load()
    ]
    assert rebuilt == _spec_table_rows()


def test_no_geocode_placeholder_survived_the_run() -> None:
    """`tier` is pre-filled and `matched_address` is a non-empty sentinel in the plan's JSON
    body, so membership and non-emptiness alone cannot catch an unreplaced row (pre-flight
    I10). The Census geocoder returns `matchedAddress` upper-cased, and the city has to appear
    in it — the cheap way to catch a match in the wrong town."""
    for h in load():
        matched = str(h["geocode"]["matched_address"])
        assert "REPLACE" not in matched, h["slug"]
        assert matched == matched.upper(), (h["slug"], matched)
        assert str(h["city"]).upper() in matched.upper(), (h["slug"], matched)


def test_community_figures_are_absent_until_the_census_plan_supplies_them() -> None:
    """D4: pop/growth/income/hh are left null; the UI shows its existing empty state."""
    for h in load():
        for field in ("pop", "growth", "income", "hh"):
            assert field not in h, (h["slug"], field)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/seeds/test_hospitals_json.py -v`
Expected: FAIL — `FileNotFoundError: … /seeds/hospitals.json`.

- [ ] **Step 3: Write the seed file**

Run the geocode block above, then create `seeds/hospitals.json`. Substitute the `lat`, `lng` and `geocode` values your run produced; every other value below is fixed by John's table (spec §2) or by D4.

```json
{
  "version": 1,
  "note": "John Dean's table of 2026-09-06, verbatim, plus the fields the V3 design needs that the table does not carry (spec 2026-09-06 D4) and coordinates from the U.S. Census Bureau Geocoder (D2, public domain, no key). Business figures are demo values John may edit at any time. No Google content.",
  "hospitals": [
    {
      "slug": "6666_dallas_veterinary_specialist_hospital",
      "name": "6666 Dallas Veterinary Specialist Hospital",
      "street": "17727 Dallas Pkwy, Suite 150", "city": "Dallas", "state": "TX", "zip": "75287",
      "phone": "(214) 555-0101", "hours": "Mon–Fri 8 AM–5 PM",
      "area": "Dallas", "market": "Dallas, TX", "type": "Specialty",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 32.991596, "lng": -96.829738,
      "geocode": {"tier": "exact", "matched_address": "17727 DALLAS PKWY, DALLAS, TX, 75287", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 2850000, "rev": 4100000, "docs": 6, "rooms": 8, "sqft": 7600, "bldg": "Included",
      "est": 2009, "listed_days_ago": 6,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "6 DVMs, 10 technicians, 8 support staff",
      "services": "Surgery, internal medicine, oncology, CT and endoscopy",
      "facility": "Owned suite in a North Dallas medical park.",
      "ownership": "Four-doctor LLC"
    },
    {
      "slug": "5555_new_york_veterinary_specialist_hospital",
      "name": "5555 New York Veterinary Specialist Hospital",
      "street": "510 E 62nd St", "city": "New York", "state": "NY", "zip": "10065",
      "phone": "(212) 555-0102", "hours": "24/7",
      "area": "New York", "market": "New York, NY", "type": "Specialty",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 3200000, "rev": 4900000, "docs": 8, "rooms": 9, "sqft": 8100, "bldg": "Leased",
      "est": 2012, "listed_days_ago": 4,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "8 DVMs, 14 technicians, 10 support staff",
      "services": "Surgery, internal medicine, cardiology, 24-hour hospitalization",
      "facility": "Two floors of a purpose-fitted Upper East Side building; lease through 2035.",
      "ownership": "Five-doctor LLC"
    },
    {
      "slug": "4444_denver_veterinary_specialist_hospital",
      "name": "4444 Denver Veterinary Specialist Hospital",
      "street": "9770 E Alameda Ave", "city": "Denver", "state": "CO", "zip": "80247",
      "phone": "(303) 555-0103", "hours": "24/7",
      "area": "Denver", "market": "Denver, CO", "type": "Specialty",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 2740000, "rev": 3900000, "docs": 6, "rooms": 8, "sqft": 7200, "bldg": "Included",
      "est": 2011, "listed_days_ago": 9,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "6 DVMs, 11 technicians, 7 support staff",
      "services": "Surgery, internal medicine, neurology, CT, 24-hour hospitalization",
      "facility": "Owned freestanding building on East Alameda with dedicated parking.",
      "ownership": "Three-doctor LLC"
    },
    {
      "slug": "3333_santa_barbara_veterinary_specialist_hospital",
      "name": "3333 Santa Barbara Veterinary Specialist Hospital",
      "street": "414 E Carrillo St", "city": "Santa Barbara", "state": "CA", "zip": "93101",
      "phone": "(805) 555-0104", "hours": "24/7",
      "area": "Santa Barbara", "market": "Santa Barbara, CA", "type": "Specialty",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 3050000, "rev": 4300000, "docs": 7, "rooms": 8, "sqft": 6900, "bldg": "Separate",
      "est": 2007, "listed_days_ago": 12,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "7 DVMs, 11 technicians, 8 support staff",
      "services": "Surgery, internal medicine, ophthalmology, ultrasound, 24-hour hospitalization",
      "facility": "Downtown building on East Carrillo; the property is available separately.",
      "ownership": "Four-doctor partnership"
    },
    {
      "slug": "2222_pet_hospital",
      "name": "2222 Pet Hospital",
      "street": "8042 Katy Freeway", "city": "Houston", "state": "TX", "zip": "77024",
      "phone": "(713) 555-0105", "hours": "24/7 emergency",
      "area": "Houston", "market": "Houston, TX", "type": "Emergency",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 3100000, "rev": 4600000, "docs": 7, "rooms": 9, "sqft": 8200, "bldg": "Leased",
      "est": 2014, "listed_days_ago": 3,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "7 DVMs, 12 technicians, 9 support staff",
      "services": "Emergency and critical care, 24-hour hospitalization, digital radiography",
      "facility": "Purpose-built emergency shell on the Katy Freeway; lease through 2034.",
      "ownership": "Three-doctor LLC"
    },
    {
      "slug": "1111_pet_hospital",
      "name": "1111 Pet Hospital",
      "street": "6565 Santa Monica Blvd", "city": "Los Angeles", "state": "CA", "zip": "90038",
      "phone": "(323) 555-0106", "hours": "24/7",
      "area": "Los Angeles", "market": "Los Angeles, CA", "type": "Small animal",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 1680000, "rev": 2400000, "docs": 3, "rooms": 6, "sqft": 4800, "bldg": "Leased",
      "est": 2003, "listed_days_ago": 5,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "3 DVMs, 6 technicians, 6 support staff",
      "services": "Wellness, dentistry, soft-tissue surgery, in-house lab, overnight nursing",
      "facility": "Corner unit on Santa Monica Boulevard with street frontage.",
      "ownership": "Sole proprietor (S-corp)"
    },
    {
      "slug": "789_lake_tahoe_pet_hospital",
      "name": "789 Lake Tahoe Pet Hospital",
      "street": "921 Emerald Bay Rd", "city": "South Lake Tahoe", "state": "CA", "zip": "96150",
      "phone": "(530) 555-0107", "hours": "Mon–Sat 8 AM–6 PM",
      "area": "South Lake Tahoe", "market": "South Lake Tahoe, CA", "type": "Small animal",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 720000, "rev": 1050000, "docs": 2, "rooms": 3, "sqft": 2600, "bldg": "Included",
      "est": 1996, "listed_days_ago": 21,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "2 DVMs, 3 technicians, 3 support staff",
      "services": "Wellness, dentistry, minor surgery, urgent care",
      "facility": "Owned building on Emerald Bay Road, remodeled 2018.",
      "ownership": "Sole proprietor"
    },
    {
      "slug": "456_pet_er",
      "name": "456 Pet ER Hospital",
      "street": "2500 N San Fernando Rd", "city": "Los Angeles", "state": "CA", "zip": "90065",
      "phone": "(323) 555-0108", "hours": "24/7",
      "area": "Los Angeles", "market": "Los Angeles, CA", "type": "Emergency",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 2900000, "rev": 4400000, "docs": 7, "rooms": 9, "sqft": 7800, "bldg": "Leased",
      "est": 2016, "listed_days_ago": 7,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "7 DVMs, 12 technicians, 8 support staff",
      "services": "Emergency and critical care, ICU, surgery, imaging",
      "facility": "Purpose-built emergency hospital on North San Fernando Road.",
      "ownership": "Three-doctor LLC"
    },
    {
      "slug": "123_route66",
      "name": "123 Route 66 Animal Hospital",
      "street": "4641 Colorado Blvd", "city": "Los Angeles", "state": "CA", "zip": "90039",
      "phone": "(818) 555-0109", "hours": "24/7",
      "area": "Los Angeles", "market": "Los Angeles, CA", "type": "Small animal",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 1240000, "rev": 1820000, "docs": 3, "rooms": 5, "sqft": 3900, "bldg": "Included",
      "est": 1991, "listed_days_ago": 14,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "3 DVMs, 5 technicians, 5 support staff",
      "services": "Wellness, dentistry, surgery, boarding, overnight nursing",
      "facility": "Owned building on Colorado Boulevard with rear parking.",
      "ownership": "Sole proprietor (LLC)"
    },
    {
      "slug": "yz_rural_animal_hospital",
      "name": "YZ Rural Animal Hospital",
      "street": "8299 E Stockton Blvd", "city": "Sacramento", "state": "CA", "zip": "95828",
      "phone": "(916) 555-0110", "hours": "24/7",
      "area": "Sacramento", "market": "Sacramento, CA", "type": "Small animal",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 980000, "rev": 1460000, "docs": 2, "rooms": 4, "sqft": 3200, "bldg": "Included",
      "est": 1999, "listed_days_ago": 10,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "2 DVMs, 4 technicians, 4 support staff",
      "services": "Wellness, dentistry, surgery, small ruminant herd health",
      "facility": "Metal building on 3 acres off Stockton Boulevard.",
      "ownership": "Sole proprietor"
    },
    {
      "slug": "vwx_veterinary_hospital",
      "name": "VWX Veterinary Hospital",
      "street": "11011 Lake Underhill Rd", "city": "Orlando", "state": "FL", "zip": "32825",
      "phone": "(407) 555-0111", "hours": "24/7",
      "area": "Orlando", "market": "Orlando, FL", "type": "Small animal",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 1150000, "rev": 1690000, "docs": 3, "rooms": 5, "sqft": 3700, "bldg": "Leased",
      "est": 2005, "listed_days_ago": 8,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "3 DVMs, 4 technicians, 5 support staff",
      "services": "Wellness, dentistry, surgery, digital radiography, overnight nursing",
      "facility": "End unit on Lake Underhill Road with covered parking.",
      "ownership": "Sole proprietor (LLC)"
    },
    {
      "slug": "stu_veterinary_specialist_center",
      "name": "STU Veterinary Specialist Center",
      "street": "2080 Principal Row", "city": "Orlando", "state": "FL", "zip": "32837",
      "phone": "(407) 555-0112", "hours": "Mon–Thu 8 AM–6 PM",
      "area": "Orlando", "market": "Orlando, FL", "type": "Specialty",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 2480000, "rev": 3500000, "docs": 5, "rooms": 7, "sqft": 6800, "bldg": "Separate",
      "est": 2013, "listed_days_ago": 16,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "5 DVMs, 9 technicians, 6 support staff",
      "services": "Surgery, internal medicine, oncology consults, CT",
      "facility": "Owned suite on Principal Row; the unit is available separately.",
      "ownership": "Three-doctor LLC"
    },
    {
      "slug": "pqr_veterinary_hospital",
      "name": "PQR Veterinary Hospital",
      "street": "9801 Old Winery Place", "city": "Sacramento", "state": "CA", "zip": "95827",
      "phone": "(916) 555-0113", "hours": "6 AM–12 AM",
      "area": "Sacramento", "market": "Sacramento, CA", "type": "Small animal",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 1320000, "rev": 1940000, "docs": 3, "rooms": 5, "sqft": 4100, "bldg": "Included",
      "est": 2001, "listed_days_ago": 11,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "3 DVMs, 5 technicians, 5 support staff",
      "services": "Wellness, dentistry, soft-tissue surgery, extended-hours urgent care",
      "facility": "Owned building at Old Winery Place, remodeled 2020.",
      "ownership": "Sole proprietor (S-corp)"
    },
    {
      "slug": "mno_pet_hospital",
      "name": "MNO Pet Hospital",
      "street": "1917 P Street", "city": "Sacramento", "state": "CA", "zip": "95811",
      "phone": "(916) 555-0114", "hours": "Mon–Fri 8 AM–6 PM; Sat 9 AM–5 PM",
      "area": "Sacramento", "market": "Sacramento, CA", "type": "Small animal",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 860000, "rev": 1280000, "docs": 2, "rooms": 4, "sqft": 2900, "bldg": "Leased",
      "est": 2008, "listed_days_ago": 18,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "2 DVMs, 3 technicians, 4 support staff",
      "services": "Wellness, dentistry, minor surgery, behaviour consults",
      "facility": "Storefront on P Street in midtown; lease assignable through 2030.",
      "ownership": "Sole proprietor (LLC)"
    },
    {
      "slug": "jkl_animal_hospital",
      "name": "JKL Animal Critical Care & ER Hospital",
      "street": "1700 Century Cir NE", "city": "Atlanta", "state": "GA", "zip": "30345",
      "phone": "(404) 555-0115", "hours": "24/7",
      "area": "Atlanta", "market": "Atlanta, GA", "type": "Emergency",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 3300000, "rev": 4800000, "docs": 8, "rooms": 10, "sqft": 8600, "bldg": "Leased",
      "est": 2015, "listed_days_ago": 2,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "8 DVMs, 13 technicians, 9 support staff",
      "services": "Emergency and critical care, ICU, surgery, CT, 24-hour hospitalization",
      "facility": "Purpose-built critical-care hospital on Century Circle; lease through 2036.",
      "ownership": "Four-doctor LLC"
    },
    {
      "slug": "ghi_veterinary_hospital",
      "name": "GHI Veterinary Hospital",
      "street": "7501 N Capital of Texas Hwy, Building A", "city": "Austin", "state": "TX", "zip": "78731",
      "phone": "(512) 555-0116", "hours": "24/7 emergency",
      "area": "Austin", "market": "Austin, TX", "type": "Emergency",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 2760000, "rev": 4050000, "docs": 6, "rooms": 8, "sqft": 7400, "bldg": "Leased",
      "est": 2017, "listed_days_ago": 13,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "6 DVMs, 11 technicians, 7 support staff",
      "services": "Emergency and critical care, 24-hour hospitalization, ultrasound",
      "facility": "Building A on North Capital of Texas Highway; lease through 2033.",
      "ownership": "Three-doctor LLC"
    },
    {
      "slug": "def_veterinary_hospital",
      "name": "DEF Veterinary Hospital",
      "street": "4434 Frontier Trail", "city": "Austin", "state": "TX", "zip": "78745",
      "phone": "(512) 555-0117", "hours": "24/7",
      "area": "Austin", "market": "Austin, TX", "type": "Small animal",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 1450000, "rev": 2100000, "docs": 3, "rooms": 5, "sqft": 4200, "bldg": "Included",
      "est": 1998, "listed_days_ago": 20,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "3 DVMs, 5 technicians, 6 support staff",
      "services": "Wellness, dentistry, soft-tissue surgery, in-house lab, overnight nursing",
      "facility": "Owned building on Frontier Trail on a half-acre lot.",
      "ownership": "Sole proprietor (S-corp)"
    },
    {
      "slug": "abc_animal_hospital",
      "name": "ABC Animal Hospital",
      "street": "6730 Airline Dr", "city": "Houston", "state": "TX", "zip": "77076",
      "phone": "(713) 555-0118", "hours": "Mon/Tue/Thu/Fri 7:30 AM–6 PM; Sat 7:30 AM–5 PM",
      "area": "Houston", "market": "Houston, TX", "type": "Small animal",
      "status": "published", "source": "seed", "location_disclosed": true,
      "lat": 0.0, "lng": 0.0,
      "geocode": {"tier": "exact", "matched_address": "REPLACE FROM THE GEOCODER RUN", "benchmark": "Public_AR_Current"},
      "demo": true,
      "price": 640000, "rev": 950000, "docs": 1, "rooms": 3, "sqft": 2400, "bldg": "Separate",
      "est": 1987, "listed_days_ago": 26,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "1 DVM, 2 technicians, 3 support staff",
      "services": "Wellness, dentistry, minor surgery, house calls",
      "facility": "Converted residence on Airline Drive; the building is available separately.",
      "ownership": "Sole proprietor"
    }
  ]
}
```

**Every `0.0` and every `REPLACE FROM THE GEOCODER RUN` above must be replaced** with the values your geocode run produced. Only the Dallas row is filled in, because only it has been probed. Leaving a `0.0` in place fails the bounds test in Step 5, which is the point.

- [ ] **Step 4: Run the shape test to verify it passes**

Run: `poetry run pytest tests/seeds/test_hospitals_json.py -v`
Expected: PASS — thirteen tests.

- [ ] **Step 5: Write the failing geocode bounds test**

Create `tests/seeds/test_geocode_bounds.py`:

```python
"""D2: "A test asserts every point lies inside its state's bounding box and within 25 km of
its city's centroid." The tables below are committed here so the test is self-contained and
never touches the network — the geocoder runs once, by hand, and its output is the data.

STATE_BBOX is the conventional bounding box of each state's land area (south, west, north,
east) in WGS-84 degrees. CITY_CENTROID is each city's civic centre. Both are reference data,
not measurements of the seeds: a seed that falls outside is a bad geocode, and the fix is to
re-geocode or to STOP and ask John — never to widen a bound (Global Constraint (l)).

Measured margin, for the implementer's information: the Dallas seed (17727 Dallas Pkwy, far
North Dallas) sits ~24.1 km from the Dallas centroid — the tightest of the eighteen against
the 25 km limit. If it fails, the coordinate is wrong, not the limit.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SEEDS = ROOT / "seeds" / "hospitals.json"
MAX_KM_FROM_CITY = 25.0
EARTH_RADIUS_KM = 6371.0088

# state: (south_lat, west_lng, north_lat, east_lng)
STATE_BBOX: dict[str, tuple[float, float, float, float]] = {
    "TX": (25.837, -106.646, 36.501, -93.508),
    "NY": (40.496, -79.763, 45.016, -71.856),
    "CO": (36.993, -109.061, 41.003, -102.041),
    "CA": (32.529, -124.482, 42.010, -114.131),
    "FL": (24.396, -87.635, 31.001, -79.974),
    "GA": (30.356, -85.605, 35.001, -80.840),
}

CITY_CENTROID: dict[str, tuple[float, float]] = {
    "Dallas, TX": (32.7767, -96.7970),
    "New York, NY": (40.7128, -74.0060),
    "Denver, CO": (39.7392, -104.9903),
    "Santa Barbara, CA": (34.4208, -119.6982),
    "Houston, TX": (29.7604, -95.3698),
    "Los Angeles, CA": (34.0522, -118.2437),
    "South Lake Tahoe, CA": (38.9332, -119.9843),
    "Sacramento, CA": (38.5816, -121.4944),
    "Orlando, FL": (28.5383, -81.3792),
    "Atlanta, GA": (33.7490, -84.3880),
    "Austin, TX": (30.2672, -97.7431),
}


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def hospitals() -> list[dict[str, object]]:
    return json.loads(SEEDS.read_text(encoding="utf-8"))["hospitals"]


def test_every_city_in_the_seed_file_has_a_committed_centroid() -> None:
    missing = {str(h["market"]) for h in hospitals()} - set(CITY_CENTROID)
    assert missing == set(), f"add a centroid for {sorted(missing)} — do not skip the check"


def test_every_state_in_the_seed_file_has_a_committed_bbox() -> None:
    missing = {str(h["state"]) for h in hospitals()} - set(STATE_BBOX)
    assert missing == set(), f"add a bounding box for {sorted(missing)} — do not skip the check"


def test_every_point_is_inside_its_states_bounding_box() -> None:
    for h in hospitals():
        south, west, north, east = STATE_BBOX[str(h["state"])]
        lat, lng = float(h["lat"]), float(h["lng"])
        assert south <= lat <= north, (h["slug"], "lat", lat, (south, north))
        assert west <= lng <= east, (h["slug"], "lng", lng, (west, east))


def test_every_point_is_within_25_km_of_its_city_centroid() -> None:
    for h in hospitals():
        km = haversine_km((float(h["lat"]), float(h["lng"])), CITY_CENTROID[str(h["market"])])
        assert km <= MAX_KM_FROM_CITY, (h["slug"], round(km, 2))


# The one coordinate verified live against the Census Geocoder (2026-09-06). `Public_AR_Current`
# is a ROLLING benchmark, so a later run can legitimately return a slightly different point.
# RECOURSE (pre-flight I9): a differing coordinate that still passes the bounding-box and 25 km
# tests above is acceptable — update this constant in the same commit and record the change in
# the hand-back note. A coordinate that fails either bound is a STOP for John. Do not delete
# this test to make a re-geocode pass; the bounds are the spec's requirement, this is the audit
# trail. Measured headroom on the committed value: 24.09 km against the 25 km limit (0.91 km).
DALLAS_ANCHOR = (32.991596, -96.829738)


def test_the_dallas_anchor_is_the_probed_coordinate() -> None:
    dallas = next(h for h in hospitals() if h["slug"] == "6666_dallas_veterinary_specialist_hospital")
    assert (dallas["lat"], dallas["lng"]) == DALLAS_ANCHOR


def test_no_two_hospitals_share_a_coordinate() -> None:
    points = [(h["lat"], h["lng"]) for h in hospitals()]
    assert len(set(points)) == len(points), "two seeds geocoded to the same point — check the run"
```

- [ ] **Step 6: Run the bounds test**

Run: `poetry run pytest tests/seeds/test_geocode_bounds.py -v`
Expected: PASS once every `0.0` has been replaced with the geocoder's answer. If a row fails the 25 km check or the bbox check, **STOP** — re-read the geocoder's `matchedAddress` for that row, and if it genuinely resolved elsewhere, report it to John. Do not raise `MAX_KM_FROM_CITY`.

- [ ] **Step 7: Run the full backend gate and commit**

```bash
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
git add seeds/hospitals.json tests/seeds/__init__.py tests/seeds/test_hospitals_json.py tests/seeds/test_geocode_bounds.py
git commit -m "feat(seeds): John's eighteen demo hospitals, geocoded by the Census Bureau

Spec 2026-09-06 §2 and D2/D4. The table is reproduced verbatim and pinned by
test_johns_table_is_reproduced_verbatim_and_in_order; type is derived exactly as D4
states (5 Specialty, 4 Emergency, 9 Small animal); the business figures are demo
values marked \"demo\": true. Coordinates come from the U.S. Census Bureau Geocoder
(public domain, no key, no Google), committed with their match tier, and are held to
their state's bounding box and 25 km of their city's centroid by a test that never
touches the network.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task L3: `scripts/prepare_photos.py` and the committed WebP files

**Files:**
- Modify: `pyproject.toml` (the one new dependency, dev group)
- Create: `scripts/prepare_photos.py`
- Create: `tests/scripts/__init__.py` (empty, pre-flight I7 — `tests/`, `tests/api/` and `tests/perf/` all have one; `tests/scripts/` has held only `.sh` files until now, and without it pytest puts `tests/scripts` on `sys.path` instead of the repo root, turning any future basename collision into an "import file mismatch")
- Create: `tests/scripts/test_prepare_photos.py`
- Create: `tests/seeds/test_photo_inventory.py`
- Create (generated, committed): `seeds/hospitals/photos/<slug>/1.webp … 4.webp`, `seeds/hospitals/photos/index.json`

**Interfaces:**
- Consumes: `seeds/hospitals.json`'s `slug` field (Task L2).
- Produces: `scripts/prepare_photos.py` exposing `MAX_PHOTOS = 4`, `MAX_EDGE_PX = 1600`, `MAX_BYTES = 250 * 1024`, `IMAGE_SUFFIXES`, `source_images(folder: Path) -> list[Path]`, `caption_of(source_name: str) -> str`, `encode(src: Path, dest: Path) -> dict[str, object]`, `prepare(source_root: Path, out_root: Path, slugs: list[str]) -> dict[str, list[dict[str, object]]]`, `sha256_of(path: Path) -> str`, `main(argv: list[str] | None = None) -> int`. Task L4 reads `seeds/hospitals/photos/index.json`; Task L5 serves the `.webp` files.

> **Pillow is the one new dependency, and it goes in the dev group.** The pipeline runs once on a developer's machine; the API serves already-encoded bytes off disk and never opens an image. The runtime image is built with `poetry install --only main`, so a main-group Pillow would add ~10 MB and a native-library surface to every api and worker container for no runtime benefit. Adding it to `[tool.poetry.group.dev.dependencies]` keeps it available to `poetry run pytest` and to the implementer, and out of production.

> **→ John — photo captions (pre-flight I2).** The design's `photoSet(p)` emits **six fixed captioned slots** chosen by `p.type` ("Reception and waiting", "Exam room", …). The API supplies **at most four** photographs in filename order, and several hospitals' first four files are all exteriors (`01_exterior_street_view`, `02_exterior_corner_view`, …), so mapping `p.photos[i]` onto slot `i` would caption an exterior photograph "Reception and waiting". **Default applied here:** `prepare_photos.py` derives a caption from each source filename (`06_interior_reception_lobby.png` → "Interior — reception lobby") and records it in `index.json` beside the SHA-256 — zero extra data entry, and the truth about each file is preserved for whichever display mapping is chosen. The display mapping itself is deliberately **not** wired up, because it cannot be until John rules on the `logic.js` question in Task L6 Step 0; when he does, the caption is already there. If John prefers slot-based selection instead (pick the file whose name matches the slot keyword rather than its position), that is a change to `source_images()`'s ordering, not to the data.

> **The source folders are read, never modified, never copied wholesale.** `/Users/johndean/Downloads/VIN FOUNDATION/Hospital images/ALL HOSPITAL SEED DATA/<slug>_individual_images/` — eighteen folders, 8 to 18 files each, `.png` and `.jpg` mixed, at least one `.DS_Store` that must be skipped. Files are named `NN_area_description.ext` (`01_exterior_front_entrance.png`, `06_interior_lobby.png`), so **folder order is `sorted()` by filename** and "the first four" means `01`–`04`.

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, add one line to `[tool.poetry.group.dev.dependencies]`:

```toml
[tool.poetry.group.dev.dependencies]
pytest = ">=8.3"
pytest-asyncio = ">=0.24"
mypy = ">=1.13"
types-psycopg2 = ">=2.9"
pyyaml = "^6.0.3"
ruff = "0.16.6"
pytest-cov = "7.1.0"
diff-cover = "10.5.1"
# The seed photograph pipeline only (scripts/prepare_photos.py, run once by hand). The API
# serves already-encoded WebP bytes off disk and never opens an image, so this must NOT move
# to the main group — the runtime image is built with `poetry install --only main`.
pillow = ">=11.0"
```

Run: `poetry lock && poetry install`
Expected: `poetry.lock` updates; `poetry run python -c "import PIL; print(PIL.__version__)"` prints a version ≥ 11.

- [ ] **Step 2: Write the failing pipeline test**

Create `tests/scripts/test_prepare_photos.py`:

```python
"""The photo pipeline (spec 2026-09-06 D3), exercised on a temp folder of GENERATED images —
never on John's originals, which this suite must not depend on being present."""
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageCms

from scripts import prepare_photos as PP

ROOT = Path(__file__).resolve().parent.parent.parent


# A REAL EXIF block (GPS included) and a REAL sRGB ICC profile, attached to the fixture sources
# so `test_metadata_is_stripped` can actually fail when the stripping is removed (pre-flight
# M2): a plain `Image.new(...).save(...)` writes no EXIF, no ICC and no XMP, so the old
# assertion held whether or not `_flattened()` re-wrapped the pixels into a fresh image.
def _metadata() -> dict[str, Any]:
    exif = Image.Exif()
    exif[0x010E] = "VIN Foundation seed source"    # ImageDescription
    exif[0x0110] = "Practice Match test camera"    # Model
    exif[0x8825] = {1: "N", 2: (30.0, 16.0, 0.0)}  # GPSInfo — the tag that must never survive
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    return {"exif": exif.tobytes(), "icc_profile": profile.tobytes()}


def _noisy(path: Path, size: tuple[int, int], *, metadata: bool = False) -> None:
    """A deliberately incompressible image: a flat colour would encode to a few hundred bytes
    and prove nothing about the 250 KB ceiling. `metadata=True` attaches the EXIF and ICC
    block above, so the stripping has something to strip."""
    import random

    rng = random.Random(path.name)
    img = Image.new("RGB", size)
    img.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(size[0] * size[1])])
    img.save(path, **(_metadata() if metadata else {}))


@pytest.fixture
def source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    folder = root / "demo_hospital_individual_images"
    folder.mkdir(parents=True)
    for i, name in enumerate(
        ["01_exterior_front.png", "02_exterior_side.jpg", "03_interior_lobby.png",
         "04_interior_exam.png", "05_interior_treatment.png", "06_interior_ward.png"], start=1
    ):
        _noisy(folder / name, (2400, 1600) if i % 2 else (1200, 2000), metadata=True)
    (folder / ".DS_Store").write_bytes(b"\x00\x01junk")
    (folder / "notes.txt").write_text("not an image")
    return root


def test_source_images_are_sorted_and_exclude_non_images(source: Path) -> None:
    names = [p.name for p in PP.source_images(source / "demo_hospital_individual_images")]
    assert names == ["01_exterior_front.png", "02_exterior_side.jpg", "03_interior_lobby.png",
                     "04_interior_exam.png", "05_interior_treatment.png", "06_interior_ward.png"]


def test_prepare_keeps_at_most_four_in_folder_order(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    index = PP.prepare(source, out, ["demo_hospital"])
    entries = index["demo_hospital"]
    assert [e["file"] for e in entries] == ["1.webp", "2.webp", "3.webp", "4.webp"]
    assert [e["source"] for e in entries] == ["01_exterior_front.png", "02_exterior_side.jpg",
                                              "03_interior_lobby.png", "04_interior_exam.png"]


def test_every_output_is_webp_within_the_dimension_and_size_ceilings(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    PP.prepare(source, out, ["demo_hospital"])
    for path in sorted((out / "demo_hospital").glob("*.webp")):
        assert path.stat().st_size <= PP.MAX_BYTES, (path.name, path.stat().st_size)
        with Image.open(path) as img:
            assert img.format == "WEBP"
            assert max(img.size) <= PP.MAX_EDGE_PX, (path.name, img.size)


def test_the_fixture_sources_really_carry_metadata(source: Path) -> None:
    """Guards the guard: if this stops holding, `test_metadata_is_stripped` below is vacuous
    again and the stripping could be deleted with a green suite (pre-flight M2)."""
    with Image.open(source / "demo_hospital_individual_images" / "02_exterior_side.jpg") as img:
        assert img.info.get("icc_profile"), "the fixture lost its ICC profile"
        assert img.getexif().get(0x0110) == "Practice Match test camera", "the fixture lost its EXIF"


def test_metadata_is_stripped(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    PP.prepare(source, out, ["demo_hospital"])
    for path in sorted((out / "demo_hospital").glob("*.webp")):
        with Image.open(path) as img:
            assert "exif" not in img.info and "icc_profile" not in img.info and "xmp" not in img.info
            assert dict(img.getexif()) == {}, (path.name, dict(img.getexif()))


def test_the_inventory_records_a_matching_sha256_and_dimensions(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    PP.prepare(source, out, ["demo_hospital"])
    index = json.loads((out / "index.json").read_text(encoding="utf-8"))
    for entry in index["hospitals"]["demo_hospital"]:
        path = out / "demo_hospital" / str(entry["file"])
        assert PP.sha256_of(path) == entry["sha256"]
        assert entry["bytes"] == path.stat().st_size
        with Image.open(path) as img:
            assert (entry["width"], entry["height"]) == img.size


@pytest.mark.parametrize(
    "name, expected",
    [("01_exterior_front_entrance.png", "Exterior — front entrance"),
     ("06_interior_reception_lobby.png", "Interior — reception lobby"),
     ("02_exterior_city_view.png", "Exterior — city view"),
     ("09_interior_treatment_surgery_area.png", "Interior — treatment surgery area"),
     ("hospital front.jpg", "Hospital front"),
     ("exterior.png", "Exterior"),
     ("01_exterior.png", "01 exterior")],
)
def test_caption_of_reads_the_curated_filename(name: str, expected: str) -> None:
    """Both arms of caption_of: the NN_area_description convention and the fallback."""
    assert PP.caption_of(name) == expected


def test_the_inventory_records_a_caption_per_photograph(source: Path, tmp_path: Path) -> None:
    index = PP.prepare(source, tmp_path / "photos", ["demo_hospital"])
    assert [e["caption"] for e in index["demo_hospital"]] == [
        "Exterior — front", "Exterior — side", "Interior — lobby", "Interior — exam"
    ]


def test_encode_gives_up_rather_than_writing_an_oversized_file(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The last rung of the quality ladder is small enough that a real photograph always fits,
    so the `raise RuntimeError` and both loop-exhaustion arcs are unreachable from real data —
    and 100 % branches is the gate (pre-flight C2). Shrinking MAX_BYTES to one byte is the
    only honest way to reach them."""
    monkeypatch.setattr(PP, "MAX_BYTES", 1)
    src = source / "demo_hospital_individual_images" / "01_exterior_front.png"
    with pytest.raises(RuntimeError) as exc:
        PP.encode(src, tmp_path / "out" / "1.webp")
    assert "01_exterior_front.png" in str(exc.value)


def test_main_returns_two_when_an_image_will_not_fit(
    source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RuntimeError is one of the two exceptions main() turns into exit 2; without this the
    `RuntimeError` half of that `except` tuple is never taken."""
    monkeypatch.setattr(PP, "MAX_BYTES", 1)
    assert PP.main(["--source", str(source), "--out", str(tmp_path / "out"), "--slugs", "demo_hospital"]) == 2


def test_a_folder_with_fewer_than_four_images_yields_what_it_has(tmp_path: Path) -> None:
    root = tmp_path / "src"
    folder = root / "thin_individual_images"
    folder.mkdir(parents=True)
    _noisy(folder / "01_only.png", (900, 600))
    index = PP.prepare(root, tmp_path / "out", ["thin"])
    assert [e["file"] for e in index["thin"]] == ["1.webp"]


def test_a_missing_folder_is_reported_not_skipped_silently(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError) as exc:
        PP.prepare(tmp_path / "src", tmp_path / "out", ["absent"])
    assert "absent_individual_images" in str(exc.value)


def test_a_small_image_is_not_upscaled(tmp_path: Path) -> None:
    root = tmp_path / "src"
    folder = root / "small_individual_images"
    folder.mkdir(parents=True)
    _noisy(folder / "01_small.png", (640, 480))
    PP.prepare(root, tmp_path / "out", ["small"])
    with Image.open(tmp_path / "out" / "small" / "1.webp") as img:
        assert img.size == (640, 480)


def test_prepare_is_idempotent_and_replaces_a_stale_output(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    first = PP.prepare(source, out, ["demo_hospital"])
    (out / "demo_hospital" / "9.webp").write_bytes(b"stale")
    second = PP.prepare(source, out, ["demo_hospital"])
    assert first == second
    assert not (out / "demo_hospital" / "9.webp").exists(), "a stale file must not survive a re-run"


def test_main_writes_the_tree_and_returns_zero(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "photos"
    code = PP.main(["--source", str(source), "--out", str(out), "--slugs", "demo_hospital"])
    assert code == 0
    assert (out / "index.json").exists() and (out / "demo_hospital" / "1.webp").exists()


def test_main_returns_two_when_a_folder_is_missing(tmp_path: Path) -> None:
    code = PP.main(["--source", str(tmp_path), "--out", str(tmp_path / "out"), "--slugs", "nope"])
    assert code == 2


def test_main_defaults_its_slugs_to_the_seed_file(source: Path, tmp_path: Path) -> None:
    """With no --slugs, main() reads seeds/hospitals.json. Proven by the eighteen real slugs
    having no folders under the temp source: it reached exit 2 by LOOKING for them."""
    assert PP.seed_slugs()[0] == "6666_dallas_veterinary_specialist_hospital"
    assert PP.main(["--source", str(source), "--out", str(tmp_path / "out")]) == 2


def test_the_module_runs_as_a_script(tmp_path: Path) -> None:
    """Covers the `if __name__ == "__main__":` guard in this process is impossible without
    runpy; a subprocess proves the entry point itself works end to end."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "prepare_photos.py"),
         "--source", str(tmp_path), "--out", str(tmp_path / "out"), "--slugs", "nope"],
        capture_output=True, text=True, check=False, cwd=ROOT,
    )
    assert result.returncode == 2


def test_the_main_guard_is_covered_in_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """runpy re-executes the file in THIS process with __name__ == "__main__", so pytest-cov
    sees the guard and its body (the subprocess above cannot report coverage back)."""
    import runpy

    monkeypatch.setattr(
        sys, "argv",
        ["prepare_photos.py", "--source", str(tmp_path), "--out", str(tmp_path / "out"), "--slugs", "nope"],
    )
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "scripts" / "prepare_photos.py"), run_name="__main__")
    assert exc.value.code == 2
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `poetry run pytest tests/scripts/test_prepare_photos.py -v`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'scripts.prepare_photos'`.

- [ ] **Step 4: Write the pipeline**

Create `scripts/prepare_photos.py`:

```python
#!/usr/bin/env python3
"""Turn John's curated hospital photograph folders into the committed WebP set the API serves
(spec 2026-09-06, D3).

Reads  <source>/<slug>_individual_images/  — up to four images in folder order (filenames are
       NN_area_description.ext, so `sorted()` IS folder order), non-images and dotfiles skipped.
Writes <out>/<slug>/1.webp … 4.webp, each ≤ 1600 px on the long edge and ≤ 250 KB, with every
       piece of metadata stripped, plus <out>/index.json carrying a SHA-256 per file.

The source folders are never modified and never copied wholesale. Pillow is a DEV dependency:
this runs once, by hand; the API only ever reads the bytes this wrote.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SEEDS_FILE = ROOT / "seeds" / "hospitals.json"
DEFAULT_SOURCE = Path.home() / "Downloads" / "VIN FOUNDATION" / "Hospital images" / "ALL HOSPITAL SEED DATA"
DEFAULT_OUT = ROOT / "seeds" / "hospitals" / "photos"
FOLDER_SUFFIX = "_individual_images"

MAX_PHOTOS = 4
MAX_EDGE_PX = 1600
MAX_BYTES = 250 * 1024
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
# Quality ladder, then a dimension step. Every rung is tried in order until one lands under
# MAX_BYTES; the last rung is small enough that a photograph cannot fail to fit.
QUALITY_LADDER = (82, 72, 62, 52, 44)
FALLBACK_EDGE_PX = 1100


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def source_images(folder: Path) -> list[Path]:
    """Every image in `folder`, in filename order. Dotfiles (.DS_Store) and non-images are out."""
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in IMAGE_SUFFIXES
    )


def caption_of(source_name: str) -> str:
    """A caption from the curated filename: `06_interior_reception_lobby.png` becomes
    "Interior — reception lobby" (pre-flight I2).

    The design's own photo slots carry six fixed captions chosen by practice type, and the API
    supplies at most four files in filename order — several hospitals' first four are all
    exteriors — so a positional mapping would mislabel them. Recording what each file actually
    shows costs nothing here and is what any display mapping will need.

    A name that does not follow the `NN_area_description.ext` convention falls back to its
    stem with underscores as spaces, capitalised."""
    stem = Path(source_name).stem
    parts = stem.split("_")
    if len(parts) >= 3 and parts[0].isdecimal():
        return f"{parts[1].capitalize()} — {' '.join(parts[2:])}"
    return stem.replace("_", " ").capitalize()


def _flattened(src: Path, max_edge: int) -> Image.Image:
    """`src` opened, EXIF-rotated, alpha flattened onto white, downscaled to `max_edge` on the
    long edge (never upscaled), and carrying no metadata — a fresh RGB image holds none."""
    with Image.open(src) as opened:
        rotated = ImageOps.exif_transpose(opened)
        rgb = rotated.convert("RGB")
    if max(rgb.size) > max_edge:
        rgb.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    clean = Image.new("RGB", rgb.size)
    clean.paste(rgb)
    return clean


def encode(src: Path, dest: Path) -> dict[str, Any]:
    """Write `src` to `dest` as WebP within both ceilings; return its inventory entry."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    for edge in (MAX_EDGE_PX, FALLBACK_EDGE_PX):
        image = _flattened(src, edge)
        for quality in QUALITY_LADDER:
            image.save(dest, format="WEBP", quality=quality, method=6)
            if dest.stat().st_size <= MAX_BYTES:
                return {
                    "file": dest.name, "source": src.name, "caption": caption_of(src.name),
                    "bytes": dest.stat().st_size, "width": image.width, "height": image.height,
                    "quality": quality, "sha256": sha256_of(dest),
                }
    raise RuntimeError(f"{src.name} will not fit in {MAX_BYTES} bytes at {FALLBACK_EDGE_PX}px/q{QUALITY_LADDER[-1]}")


def prepare(source_root: Path, out_root: Path, slugs: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Encode every slug's first `MAX_PHOTOS` photographs and write `out_root/index.json`."""
    index: dict[str, list[dict[str, Any]]] = {}
    for slug in slugs:
        folder = source_root / (slug + FOLDER_SUFFIX)
        if not folder.is_dir():
            raise FileNotFoundError(f"no photograph folder {folder}")
        destination = out_root / slug
        if destination.exists():
            shutil.rmtree(destination)  # a re-run must not leave a stale Nth file behind
        entries = [
            encode(src, destination / f"{n}.webp")
            for n, src in enumerate(source_images(folder)[:MAX_PHOTOS], start=1)
        ]
        index[slug] = entries
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "index.json").write_text(
        json.dumps(
            {"version": 1, "max_photos": MAX_PHOTOS, "max_edge_px": MAX_EDGE_PX,
             "max_bytes": MAX_BYTES, "hospitals": index},
            indent=2, sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return index


def seed_slugs() -> list[str]:
    return [str(h["slug"]) for h in json.loads(SEEDS_FILE.read_text(encoding="utf-8"))["hospitals"]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare the seed hospital photographs (spec D3).")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--slugs", nargs="*", default=None)
    args = parser.parse_args(argv)
    slugs = args.slugs if args.slugs else seed_slugs()
    try:
        index = prepare(args.source, args.out, list(slugs))
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"[photos] {exc}", file=sys.stderr)
        return 2
    total = sum(int(e["bytes"]) for entries in index.values() for e in entries)
    print(f"[photos] {sum(len(e) for e in index.values())} files, {total / 1024 / 1024:.1f} MB → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the pipeline test to verify it passes**

Run: `poetry run pytest tests/scripts/test_prepare_photos.py -v`
Expected: PASS — thirteen tests.

- [ ] **Step 6: Produce the committed photographs**

```bash
cd "/Users/johndean/Development/Practice Match"
poetry run python scripts/prepare_photos.py \
  --source "/Users/johndean/Downloads/VIN FOUNDATION/Hospital images/ALL HOSPITAL SEED DATA"
du -sh seeds/hospitals/photos
find seeds/hospitals/photos -name '*.webp' | wc -l
```
Expected: `[photos] 72 files, <N> MB → …`; **exactly 72 files** (18 × 4); the directory total **≤ 18 MB** (the arithmetic ceiling is 72 × 250 KB = 17.6 MB; D3 estimates ≈ 15 MB). If it exceeds 18 MB something has bypassed `MAX_BYTES` — **STOP**.

72 is a hard expectation, not an estimate: every one of the eighteen curated folders holds between 8 and 18 images today (195 in total), so all eighteen yield four. The pipeline *handles* a folder with fewer than four — `test_a_folder_with_fewer_than_four_images_yields_what_it_has` pins that — but **a count below 72 means a folder changed under you: STOP and report it** rather than committing a short set. A missing folder is exit 2 and also a STOP (pre-flight M3).

- [ ] **Step 7: Write the failing committed-output test**

Create `tests/seeds/test_photo_inventory.py`:

```python
"""The committed photographs match their inventory and stay inside the size ceiling (D3).

This is the gate that catches a hand-edited WebP, a file added without re-running the pipeline
and an inventory that drifted from the tree. It reads only what is committed — no source
folders, no network, no Pillow re-encode.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PHOTOS = ROOT / "seeds" / "hospitals" / "photos"
INDEX = PHOTOS / "index.json"
TOTAL_CEILING_BYTES = 18 * 1024 * 1024  # 72 files x 250 KB = 17.6 MB; D3 estimates ~15 MB
MAX_BYTES = 250 * 1024
MAX_PHOTOS = 4


def inventory() -> dict[str, list[dict[str, object]]]:
    return json.loads(INDEX.read_text(encoding="utf-8"))["hospitals"]


def seed_slugs() -> list[str]:
    data = json.loads((ROOT / "seeds" / "hospitals.json").read_text(encoding="utf-8"))
    return [str(h["slug"]) for h in data["hospitals"]]


def test_every_seeded_hospital_has_photographs() -> None:
    inv = inventory()
    for slug in seed_slugs():
        assert slug in inv and 1 <= len(inv[slug]) <= MAX_PHOTOS, slug


def test_the_inventory_names_no_hospital_that_is_not_seeded() -> None:
    assert set(inventory()) == set(seed_slugs())


def test_every_committed_file_matches_its_recorded_hash_and_size() -> None:
    for slug, entries in inventory().items():
        for entry in entries:
            path = PHOTOS / slug / str(entry["file"])
            data = path.read_bytes()
            assert hashlib.sha256(data).hexdigest() == entry["sha256"], path
            assert len(data) == entry["bytes"] == path.stat().st_size, path
            assert len(data) <= MAX_BYTES, (path, len(data))


def test_the_tree_holds_nothing_the_inventory_does_not_name() -> None:
    on_disk = {f"{p.parent.name}/{p.name}" for p in PHOTOS.rglob("*.webp")}
    named = {f"{slug}/{e['file']}" for slug, entries in inventory().items() for e in entries}
    assert on_disk == named


def test_every_committed_photograph_has_a_caption_and_a_source() -> None:
    """What each file actually shows, recorded at pipeline time (pre-flight I2). The display
    mapping is John's call (Task L6 Step 0); the data is here either way."""
    for slug, entries in inventory().items():
        for entry in entries:
            assert isinstance(entry["caption"], str) and entry["caption"], (slug, entry["file"])
            assert isinstance(entry["source"], str) and entry["source"], (slug, entry["file"])


def test_files_are_numbered_from_one_without_gaps() -> None:
    for slug, entries in inventory().items():
        assert [e["file"] for e in entries] == [f"{n}.webp" for n in range(1, len(entries) + 1)], slug


def test_the_committed_set_stays_under_the_size_ceiling() -> None:
    total = sum(p.stat().st_size for p in PHOTOS.rglob("*.webp"))
    assert total <= TOTAL_CEILING_BYTES, f"{total / 1024 / 1024:.1f} MB committed"
```

- [ ] **Step 8: Run it, then the full gate**

```bash
poetry run pytest tests/seeds/test_photo_inventory.py -v
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
```
Expected: all green.

- [ ] **Step 9: Commit**

```bash
cd "/Users/johndean/Development/Practice Match"
git add pyproject.toml poetry.lock scripts/prepare_photos.py \
        tests/scripts/__init__.py tests/scripts/test_prepare_photos.py \
        tests/seeds/test_photo_inventory.py seeds/hospitals/photos
git commit -m "feat(seeds): photo pipeline and the committed WebP set

Spec 2026-09-06 D3: up to four photographs per hospital in folder order, WebP at
<= 1600 px on the long edge and <= 250 KB, every piece of metadata stripped, with a
SHA-256 inventory. Pillow is the one new dependency and lives in the DEV group — the
runtime image is built with `poetry install --only main` and the API only reads bytes.
The committed tree is held to its inventory and to an 18 MB ceiling by a test that
never opens an image.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task L4: `scripts/seed_listings.py` and the `seed` container role

**Files:**
- Create: `scripts/seed_listings.py`
- Create: `tests/scripts/test_seed_listings.py`
- Modify: `scripts/start.sh` (add the `seed` role; update the unknown-role message)
- Modify: `tests/scripts/test_start_sh.sh`
- Modify: `Dockerfile` (`COPY seeds/ ./seeds/`)
- Modify: `tests/test_build_config.py`
- Modify: `scripts/verify-image.sh` (prove the files are really in the image, not just in the Dockerfile's text)
- Modify: `tests/scripts/test_verify_image_sh.sh`
- Modify: `DEPLOY.md` (a "Seeding QA" section)
- Modify: `tests/test_docs.py`

**Interfaces:**
- Consumes: `migrations/015_listing.sql`'s `listing` table (L1); `seeds/hospitals.json` (L2); `seeds/hospitals/photos/index.json` (L3). It imports **nothing from `scripts/`** — see the `normalize_dsn` docstring in Step 3 and the runnability note below.
- Produces: `scripts/seed_listings.py` exposing `SEEDS_FILE`, `PHOTO_INDEX`, `UPSERT`, `normalize_dsn(dsn: str) -> str`, `load_seed(path: Path) -> list[dict[str, Any]]`, `photo_paths(slug: str, index: dict[str, Any]) -> list[str]`, `row_params(hospital: dict[str, Any], photos: list[str]) -> dict[str, Any]`, `seed(dsn: str, *, reset: bool = False) -> int` (returns the number of rows upserted), `main(argv: list[str] | None = None) -> int`. Exit codes: `0` success, `2` `DATABASE_URL` unset, `3` database unreachable, `4` seed data missing or malformed. Task L5 reads the rows it writes.

> **⚠️ This file must be importable AND runnable as a bare script.** `tests/scripts/test_seed_listings.py` imports it as `scripts.seed_listings` (pytest puts the repo root on `sys.path`), while the container runs `python scripts/seed_listings.py`, which puts `/app/scripts` on `sys.path[0]` and the repo root nowhere. `scripts/` has no `__init__.py`, the project is `package-mode = false`, and the image installs `--no-root`, so **any `from scripts.… import …` here is a QA-only crash that every test in this plan would miss** (pre-flight C1). The rule: this file imports stdlib and `psycopg2` only, exactly as `scripts/migrate.py` does. Step 5's subprocess test is what holds it to that. (`python -m scripts.seed_listings` from `/app` would also work — namespace packages make `scripts` importable when the repo root *is* `sys.path[0]` — but the plain-path invocation is what `start.sh` and DEPLOY.md use, so the plain-path invocation is what is tested.)

> **Idempotent by `slug`, with `--reset` for a clean sweep** (D7). A second run of the plain command changes nothing but `updated_at`; `--reset` deletes every `source='seed'` row first, which is what turns QA's design fixtures into the eighteen and nothing else. `source='seller'` rows are never touched by either path — that is the whole point of the column.

> **`listed_at` is computed at seed time** from `listed_days_ago`, so the seeds never read as a year old. `geom` is built with `ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography` — **longitude first**; PostGIS's `ST_MakePoint` takes `(x, y)`, and `x` is longitude. Getting this backwards puts every hospital in the Indian Ocean and passes every unit test that does not read the geometry back, which is why the test in Step 1 reads latitude and longitude back out of `geom` and compares them to the seed file.

- [ ] **Step 1: Write the failing seeder test**

Create `tests/scripts/test_seed_listings.py`:

```python
"""scripts/seed_listings.py against a scratch database (spec 2026-09-06 D7)."""
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import psycopg2
import pytest

from scripts import seed_listings as SL

ROOT = Path(__file__).resolve().parent.parent.parent


def _count(dsn: str, where: str = "TRUE") -> int:
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        # `where` is always a literal written in this file — never a value from a request.
        cur.execute(f"SELECT count(*) FROM listing WHERE {where}")
        return int(cur.fetchone()[0])


def test_seed_writes_eighteen_published_seed_rows(scratch_dsn: str) -> None:
    assert SL.seed(scratch_dsn) == 18
    assert _count(scratch_dsn) == 18
    assert _count(scratch_dsn, "source = 'seed' AND status = 'published'") == 18


def test_seed_is_idempotent(scratch_dsn: str) -> None:
    SL.seed(scratch_dsn)
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT id, created_at FROM listing ORDER BY slug")
        before = cur.fetchall()
    assert SL.seed(scratch_dsn) == 18
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT id, created_at FROM listing ORDER BY slug")
        after = cur.fetchall()
    assert _count(scratch_dsn) == 18
    assert after == before, "an upsert by slug must keep the same row, id and created_at"


def test_reset_removes_seed_rows_but_never_seller_rows(scratch_dsn: str) -> None:
    SL.seed(scratch_dsn)
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, status)"
            " VALUES ('sellers-own','Seller listing','Austin','TX','Austin','Small animal','Austin, TX','seller','published')"
        )
    assert SL.seed(scratch_dsn, reset=True) == 18
    assert _count(scratch_dsn, "source = 'seed'") == 18
    assert _count(scratch_dsn, "source = 'seller'") == 1


def test_every_row_carries_the_seed_files_own_values(scratch_dsn: str) -> None:
    SL.seed(scratch_dsn)
    hospitals = {h["slug"]: h for h in SL.load_seed(SL.SEEDS_FILE)}
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT slug, name, street, city, state, zip, phone, hours, area, market, type, status,"
            " source, location_disclosed, price, rev, docs, rooms, sqft, bldg, est, note, staff,"
            " services, facility, ownership FROM listing"
        )
        for row in cur.fetchall():
            h = hospitals[row[0]]
            assert row[1:14] == (
                h["name"], h["street"], h["city"], h["state"], h["zip"], h["phone"], h["hours"],
                h["area"], h["market"], h["type"], "published", "seed", True,
            ), h["slug"]
            assert row[14:] == (
                h["price"], h["rev"], h["docs"], h["rooms"], h["sqft"], h["bldg"], h["est"],
                h["note"], h["staff"], h["services"], h["facility"], h["ownership"],
            ), h["slug"]


def test_the_point_is_stored_longitude_first(scratch_dsn: str) -> None:
    """ST_MakePoint takes (x, y) = (lng, lat). Swapping them passes every test that does not
    read the geometry back — so this one reads it back."""
    SL.seed(scratch_dsn)
    hospitals = {h["slug"]: h for h in SL.load_seed(SL.SEEDS_FILE)}
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT slug, ST_Y(geom::geometry), ST_X(geom::geometry) FROM listing")
        for slug, lat, lng in cur.fetchall():
            assert round(float(lat), 6) == hospitals[slug]["lat"], slug
            assert round(float(lng), 6) == hospitals[slug]["lng"], slug


def test_listed_at_is_computed_from_listed_days_ago(scratch_dsn: str) -> None:
    SL.seed(scratch_dsn)
    hospitals = {h["slug"]: h for h in SL.load_seed(SL.SEEDS_FILE)}
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT slug, EXTRACT(DAY FROM now() - listed_at)::int FROM listing")
        for slug, days in cur.fetchall():
            assert days == hospitals[slug]["listed_days_ago"], slug


def test_photos_come_from_the_committed_inventory(scratch_dsn: str) -> None:
    SL.seed(scratch_dsn)
    index = json.loads(SL.PHOTO_INDEX.read_text(encoding="utf-8"))["hospitals"]
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT slug, photos FROM listing")
        for slug, photos in cur.fetchall():
            assert photos == [f"{slug}/{e['file']}" for e in index[slug]], slug
            assert 1 <= len(photos) <= 4, slug


def test_main_seeds_from_the_environment(scratch_dsn: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert SL.main([]) == 0
    assert _count(scratch_dsn) == 18
    assert SL.main(["--reset"]) == 0
    assert _count(scratch_dsn) == 18


def test_main_returns_two_without_a_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert SL.main([]) == 2


def test_main_returns_three_when_the_database_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    assert SL.main([]) == 3


def test_main_returns_four_when_the_seed_file_is_malformed(
    scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = tmp_path / "hospitals.json"
    broken.write_text('{"version": 1}', encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(SL, "SEEDS_FILE", broken)
    assert SL.main([]) == 4


def test_main_returns_four_when_the_seed_file_is_absent(
    scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(SL, "SEEDS_FILE", tmp_path / "absent.json")
    assert SL.main([]) == 4


def test_photo_paths_is_empty_for_an_unknown_slug() -> None:
    assert SL.photo_paths("not-a-hospital", {"hospitals": {}}) == []


def test_normalize_dsn_agrees_with_the_migration_runner() -> None:
    """scripts/seed_listings.py duplicates normalize_dsn because it must run as a bare script
    inside the container (pre-flight C1). This pins the copy to the original. The runner is
    loaded by file path, the way tests/test_migrate.py already loads it."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("migrate_probe", ROOT / "scripts" / "migrate.py")
    assert spec is not None and spec.loader is not None
    migrate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migrate)
    for dsn in (
        "postgres://u:p@h:5432/db",
        "postgresql://u:p@h:5432/db",
        "postgresql+asyncpg://u:p@h:5432/db",
        "postgresql://u:p@h:5432/db?sslmode=require",
    ):
        assert SL.normalize_dsn(dsn) == migrate.normalize_dsn(dsn), dsn


def test_the_module_runs_as_a_bare_script_from_the_repo_root() -> None:
    """The container runs `python scripts/seed_listings.py`, which puts scripts/ — not the repo
    root — on sys.path. A package-relative import in this file is a QA-only crash that neither
    pytest nor runpy would catch, because both already have the repo root on the path
    (pre-flight C1). This is the test that would have caught it."""
    import os

    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "seed_listings.py")],
        capture_output=True, text=True, check=False, cwd=ROOT, env=env,
    )
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert "DATABASE_URL" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr and "Traceback" not in result.stderr


def test_the_module_runs_as_a_bare_script_from_any_working_directory(tmp_path: Path) -> None:
    """`railway ssh` drops the operator into /app, but a one-off Railway service command can
    start anywhere. ROOT is resolved from __file__, so neither the seed file nor the photo
    inventory depends on the working directory."""
    import os

    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "seed_listings.py")],
        capture_output=True, text=True, check=False, cwd=tmp_path, env=env,
    )
    assert result.returncode == 2, result.stderr


def test_main_returns_four_when_the_seed_file_has_no_hospitals(
    scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `not isinstance(...) or not hospitals` arm of load_seed — the two exit-4 tests above
    reach the `except` clause instead (pre-flight C2)."""
    empty = tmp_path / "hospitals.json"
    empty.write_text('{"version": 1, "hospitals": []}', encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(SL, "SEEDS_FILE", empty)
    assert SL.main([]) == 4


def test_main_returns_four_when_the_hospitals_key_is_not_a_list(
    scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of the same `or` (pre-flight C2)."""
    wrong = tmp_path / "hospitals.json"
    wrong.write_text('{"version": 1, "hospitals": {"a": 1}}', encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(SL, "SEEDS_FILE", wrong)
    assert SL.main([]) == 4


def test_main_returns_four_when_the_photo_inventory_is_absent(
    scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_photo_index's own `raise SeedDataError` — nothing else perturbs PHOTO_INDEX
    (pre-flight C2)."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(SL, "PHOTO_INDEX", tmp_path / "absent.json")
    assert SL.main([]) == 4


def test_row_params_names_the_missing_field() -> None:
    """row_params' `except KeyError` arm (pre-flight C2)."""
    with pytest.raises(SL.SeedDataError) as exc:
        SL.row_params({"slug": "x"}, [])
    assert "x" in str(exc.value) and "name" in str(exc.value)


def test_the_main_guard_is_covered(monkeypatch: pytest.MonkeyPatch) -> None:
    """runpy re-executes the file in THIS process with __name__ == "__main__", so pytest-cov
    sees the guard; the subprocess tests above prove the same entry point works when the repo
    root is NOT on sys.path, which coverage can never see."""
    import runpy

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["seed_listings.py"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "scripts" / "seed_listings.py"), run_name="__main__")
    assert exc.value.code == 2
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `poetry run pytest tests/scripts/test_seed_listings.py -v`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'scripts.seed_listings'`.

- [ ] **Step 3: Write the seeder**

Create `scripts/seed_listings.py`:

```python
#!/usr/bin/env python3
"""Seed (or re-seed) the eighteen demo hospitals into a Practice Match database.

Idempotent: an upsert keyed on `slug`, so a second run changes nothing but `updated_at`.
`--reset` deletes every `source='seed'` row first — that is what turns QA's design fixtures
into the eighteen and nothing else; a seller's own listing (`source='seller'`) is never
touched by either path.

Runs inside the api container: `railway ssh --service api --environment QA` then
`python scripts/seed_listings.py --reset`, or as the `seed` role of scripts/start.sh.
Never on production without John's go (spec 2026-09-06 D7).

Exit codes mirror scripts/migrate.py: 0 done, 2 DATABASE_URL unset, 3 database unreachable
(retryable), 4 the seed data is missing or malformed (not retryable).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
SEEDS_FILE = ROOT / "seeds" / "hospitals.json"
PHOTO_INDEX = ROOT / "seeds" / "hospitals" / "photos" / "index.json"


def normalize_dsn(dsn: str) -> str:
    """The same normalisation as `scripts/migrate.normalize_dsn`, duplicated here deliberately.

    The container runs this file as `python scripts/seed_listings.py`, which puts `/app/scripts`
    on `sys.path[0]` — **not** `/app`. `scripts/` has no `__init__.py`, the project is
    `package-mode = false` and the image installs with `--no-root`, so nothing ever puts the
    repo root on the path: `from scripts.migrate import ...` raises ModuleNotFoundError the
    moment the seed role runs, and no test catches it (pytest and `runpy.run_path` both start
    with the repo root already on the path). `scripts/migrate.py` works in the container for
    exactly this reason — it imports nothing but stdlib and psycopg2.

    Twelve lines of duplication instead of a `sys.path` mutation, and
    `test_normalize_dsn_agrees_with_the_migration_runner` pins the two to the same answers."""
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


UPSERT = """
INSERT INTO listing (
  slug, name, street, city, state, zip, phone, hours, status, location_disclosed,
  geom, area, type, market, price, rev, docs, rooms, sqft, bldg, est, listed_at,
  note, staff, services, facility, ownership, photos, source, updated_at
) VALUES (
  %(slug)s, %(name)s, %(street)s, %(city)s, %(state)s, %(zip)s, %(phone)s, %(hours)s,
  %(status)s, %(location_disclosed)s,
  ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography,
  %(area)s, %(type)s, %(market)s, %(price)s, %(rev)s, %(docs)s, %(rooms)s, %(sqft)s,
  %(bldg)s, %(est)s, now() - make_interval(days => %(listed_days_ago)s),
  %(note)s, %(staff)s, %(services)s, %(facility)s, %(ownership)s,
  %(photos)s::jsonb, 'seed', now()
)
ON CONFLICT (slug) DO UPDATE SET
  name = EXCLUDED.name, street = EXCLUDED.street, city = EXCLUDED.city, state = EXCLUDED.state,
  zip = EXCLUDED.zip, phone = EXCLUDED.phone, hours = EXCLUDED.hours, status = EXCLUDED.status,
  location_disclosed = EXCLUDED.location_disclosed, geom = EXCLUDED.geom, area = EXCLUDED.area,
  type = EXCLUDED.type, market = EXCLUDED.market, price = EXCLUDED.price, rev = EXCLUDED.rev,
  docs = EXCLUDED.docs, rooms = EXCLUDED.rooms, sqft = EXCLUDED.sqft, bldg = EXCLUDED.bldg,
  est = EXCLUDED.est, listed_at = EXCLUDED.listed_at, note = EXCLUDED.note,
  staff = EXCLUDED.staff, services = EXCLUDED.services, facility = EXCLUDED.facility,
  ownership = EXCLUDED.ownership, photos = EXCLUDED.photos, updated_at = now()
"""


class SeedDataError(Exception):
    """The seed file or the photo inventory is missing or does not carry what it must."""


def load_seed(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        hospitals = data["hospitals"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SeedDataError(f"{path}: {type(exc).__name__}") from None
    if not isinstance(hospitals, list) or not hospitals:
        raise SeedDataError(f"{path}: no hospitals")
    return [dict(h) for h in hospitals]


def load_photo_index(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SeedDataError(f"{path}: {type(exc).__name__}") from None
    return dict(loaded)


def photo_paths(slug: str, index: dict[str, Any]) -> list[str]:
    """Relative paths under seeds/hospitals/photos/, in inventory order."""
    entries = index.get("hospitals", {}).get(slug, [])
    return [f"{slug}/{entry['file']}" for entry in entries]


def row_params(hospital: dict[str, Any], photos: list[str]) -> dict[str, Any]:
    keys = (
        "slug", "name", "street", "city", "state", "zip", "phone", "hours", "status",
        "location_disclosed", "lat", "lng", "area", "type", "market", "price", "rev",
        "docs", "rooms", "sqft", "bldg", "est", "listed_days_ago", "note", "staff",
        "services", "facility", "ownership",
    )
    try:
        params: dict[str, Any] = {key: hospital[key] for key in keys}
    except KeyError as exc:
        raise SeedDataError(f"{hospital.get('slug', '?')}: missing {exc}") from None
    params["photos"] = json.dumps(photos)
    return params


def seed(dsn: str, *, reset: bool = False) -> int:
    hospitals = load_seed(SEEDS_FILE)
    index = load_photo_index(PHOTO_INDEX)
    rows = [row_params(h, photo_paths(str(h["slug"]), index)) for h in hospitals]
    conn = psycopg2.connect(normalize_dsn(dsn))
    try:
        with conn, conn.cursor() as cur:
            if reset:
                cur.execute("DELETE FROM listing WHERE source = 'seed'")
                print(f"  - removed {cur.rowcount} existing seed listings")
            for params in rows:
                cur.execute(UPSERT, params)
    finally:
        conn.close()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the demo hospitals (spec 2026-09-06 D7).")
    parser.add_argument("--reset", action="store_true", help="delete every source='seed' row first")
    args = parser.parse_args(argv)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("[seed] DATABASE_URL is not set", file=sys.stderr)
        return 2
    try:
        count = seed(dsn, reset=args.reset)
    except SeedDataError as exc:
        print(f"[seed] seed data unusable: {exc}", file=sys.stderr)
        return 4
    except psycopg2.OperationalError as exc:
        print(f"[seed] database unreachable: {type(exc).__name__}", file=sys.stderr)
        return 3
    print(f"[seed] done - {count} listings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the seeder test to verify it passes**

Run: `poetry run pytest tests/scripts/test_seed_listings.py -v`
Expected: PASS — fourteen tests.

- [ ] **Step 5: Write the failing `seed` role test**

In `tests/scripts/test_start_sh.sh`, insert these three lines immediately **before** the `if DRY_RUN=1 bash scripts/start.sh bogus …` line at the end:

```bash
out=$(DRY_RUN=1 bash scripts/start.sh seed) || fail "seed role exited non-zero"
[[ "$out" == *"python scripts/seed_listings.py"* ]] || fail "seed role should run the seeder, got: $out"
[[ "$out" != *uvicorn* && "$out" != *celery* ]] || fail "the seed role must not start a server, got: $out"
```

Run: `bash tests/scripts/test_start_sh.sh`
Expected: FAIL — `unknown role: seed (expected api | worker | migrate)`.

- [ ] **Step 6: Add the `seed` role**

In `scripts/start.sh`, insert a new case arm immediately after the `migrate)` arm and before the `*)` arm, and update the unknown-role message:

```bash
  migrate)
    mcmd=(python scripts/migrate.py)
    if [[ "${DRY_RUN:-0}" == "1" ]]; then echo "${mcmd[*]}"; else exec "${mcmd[@]}"; fi
    ;;
  seed)
    # One-shot: load the eighteen demo hospitals (spec 2026-09-06 D7). Run by hand inside the
    # api container (`railway ssh`) or as a one-off service command; never on production
    # without John's go. Arguments after the role are passed through, so `start.sh seed --reset`
    # sweeps the existing seed rows first.
    shift || true
    scmd=(python scripts/seed_listings.py "$@")
    if [[ "${DRY_RUN:-0}" == "1" ]]; then echo "${scmd[*]}"; else exec "${scmd[@]}"; fi
    ;;
  *)
    echo "unknown role: $role (expected api | worker | migrate | seed)" >&2; exit 2 ;;
```

> `shift || true`: the role can also be selected without a positional argument (via `RAILWAY_SERVICE_NAME`), in which case there is nothing to shift and a bare `shift` would fail under `set -e`.

Run: `bash tests/scripts/test_start_sh.sh`
Expected: `start.sh dispatcher OK`.

- [ ] **Step 7: Ship the seed data in the image (RED → GREEN)**

Append to `tests/test_build_config.py`:

```python
def test_dockerfile_ships_the_seed_data_and_photographs():
    """scripts/seed_listings.py runs inside the api container and app/api/listings.py serves
    the WebP files off disk, so seeds/ must be in the image (spec 2026-09-06 D3/D7)."""
    d = (ROOT / "Dockerfile").read_text()
    assert "COPY seeds/ ./seeds/" in d


def test_seed_data_is_not_ignored_by_the_image_or_upload_filters():
    for name in (".railwayignore", ".dockerignore"):
        entries = (ROOT / name).read_text().split()
        assert not any(e.rstrip("/") == "seeds" for e in entries), f"{name} excludes seeds/"
```

Run: `poetry run pytest tests/test_build_config.py -v`
Expected: FAIL — `assert "COPY seeds/ ./seeds/" in d`.

In `Dockerfile`, add one line in the runtime stage, immediately after `COPY scripts/ ./scripts/`:

```dockerfile
COPY app/ ./app/
COPY migrations/ ./migrations/
COPY scripts/ ./scripts/
# The eighteen demo hospitals and their photographs (spec 2026-09-06 D3/D7): the `seed` role
# reads seeds/hospitals.json in-container, and GET /api/listings/{id}/photos/{n} serves the
# committed WebP files from seeds/hospitals/photos/. ~15 MB.
COPY seeds/ ./seeds/
COPY --from=frontend-build /work/frontend/dist/ ./frontend/dist/
```

> The existing `test_dockerfile_runs_as_a_non_root_user_declared_after_the_last_copy` requires `USER app` after the last `COPY`; this line sits well before it, so that test keeps passing. Re-run it to be sure.

Run: `poetry run pytest tests/test_build_config.py -v`
Expected: PASS.

- [ ] **Step 7b: Prove the files are in the RUNNING image, not just in the Dockerfile's text**

`test_dockerfile_ships_the_seed_data_and_photographs` greps a text file. A `.dockerignore` entry added later, a build-context change or a typo in the path would leave the assertion green and the container empty (pre-flight I8). `scripts/verify-image.sh` already runs the built image; extend it.

In `tests/scripts/test_verify_image_sh.sh`, add `"seed data in image OK"` to the expected-output list:

```bash
for line in "api healthz OK" "index.html served" "SPA fallback OK" "worker health OK" "celery booted" "non-root OK" "seed data in image OK" "coming soon OK"; do
```

and append a third case at the end of the file, after the O1 negative case:

```bash
# --- I8: a seeds/ directory missing from the image must fail the script ---
cat > "$FAKE_BIN/docker" <<'DOCKEREOF3'
#!/usr/bin/env bash
echo "docker $*" >> "$FAKE_LOG"
case "$1" in
  build) exit 0 ;;
  run) echo fake0000container ;;
  rm) exit 0 ;;
  exec) if [[ "$*" == *"test -f"* ]]; then exit 1; fi; echo 10001 ;;
  logs) echo "fake celery@fakehost ready." ;;
  *) exit 0 ;;
esac
DOCKEREOF3
chmod +x "$FAKE_BIN/docker"
: > "$FAKE_LOG"

set +e
PATH="$FAKE_BIN:$PATH" bash scripts/verify-image.sh > "$WORKDIR/out3" 2>&1
code3=$?
set -e

[[ $code3 -ne 0 ]] || { cat "$WORKDIR/out3"; fail "verify-image.sh must fail when seeds/ is missing from the image; it exited 0"; }
out3=$(cat "$WORKDIR/out3")
[[ "$out3" == *"FAIL: seeds/hospitals.json missing from the image"* ]] || fail "the missing-seeds failure must name the file; got: $out3"

echo "verify-image.sh seed-data negative case OK (I8)"
```

Run: `bash tests/scripts/test_verify_image_sh.sh`
Expected: FAIL — `missing expected output line: seed data in image OK`.

In `scripts/verify-image.sh`, insert immediately after the `echo "non-root OK"` line:

```bash
# The seeder reads seeds/hospitals.json in-container and the photo endpoint serves
# seeds/hospitals/photos/*.webp off disk, so the Dockerfile's COPY has to have actually
# landed. Grepping the Dockerfile proves nothing about the built image.
for seed_file in seeds/hospitals.json seeds/hospitals/photos/index.json; do
  docker exec pm-api test -f "$seed_file" || { echo "FAIL: $seed_file missing from the image" >&2; exit 1; }
done
echo "seed data in image OK"
```

Run: `bash tests/scripts/test_verify_image_sh.sh`
Expected: `verify-image.sh dispatcher OK`, `verify-image.sh negative case OK (O1)`, `verify-image.sh seed-data negative case OK (I8)`.

- [ ] **Step 8: Document the operation (RED → GREEN)**

Append to `tests/test_docs.py`:

```python
def test_deploy_md_documents_how_to_seed_qa():
    """The seed run is a hand operation on QA; DEPLOY.md is where hand operations live."""
    deploy = (ROOT / "DEPLOY.md").read_text()
    assert "## Seeding the demo hospitals (QA)" in deploy
    assert "python scripts/seed_listings.py --reset" in deploy
    assert "never on production without John's go" in deploy
```

Run: `poetry run pytest tests/test_docs.py -v`
Expected: FAIL — the section does not exist.

In `DEPLOY.md`, add this section immediately **before** `## Rollback`:

````markdown
## Seeding the demo hospitals (QA)

The eighteen demo hospitals (`seeds/hospitals.json`, spec 2026-09-06) are loaded by
`scripts/seed_listings.py`, which ships in the image together with `seeds/`. It is idempotent
(upsert by `slug`); `--reset` deletes every `source='seed'` row first and leaves any
`source='seller'` row alone. It is a hand operation and it is **never on production without
John's go**.

```bash
railway status                                   # MUST print Project: Practice Match
railway ssh --service api --environment QA       # John's ed25519 key; the CLI needs a key on file
python scripts/seed_listings.py --reset          # inside the container
# expected: "  - removed N existing seed listings" then "[seed] done - 18 listings"
```

Exit codes: `0` done · `2` `DATABASE_URL` unset · `3` database unreachable (retry) · `4` the
seed data is missing or malformed (fix the file, redeploy). Anything else — in particular a
traceback — means the image is wrong, not the data. The same run is available as a container
role: `bash scripts/start.sh seed --reset`, for a one-off Railway service command.
`python -m scripts.seed_listings --reset` works too, from `/app`.
````

Run: `poetry run pytest tests/test_docs.py -v`
Expected: PASS.

- [ ] **Step 9: Run the full gate**

```bash
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
bash tests/scripts/test_start_sh.sh
bash tests/scripts/test_deploy_guard.sh
bash tests/scripts/test_verify_deploy.sh
bash tests/scripts/test_verify_image_sh.sh
```
Expected: all green, all four shell suites print OK.

- [ ] **Step 10: Commit**

```bash
cd "/Users/johndean/Development/Practice Match"
git add scripts/seed_listings.py tests/scripts/test_seed_listings.py \
        scripts/start.sh tests/scripts/test_start_sh.sh \
        Dockerfile tests/test_build_config.py scripts/verify-image.sh \
        tests/scripts/test_verify_image_sh.sh DEPLOY.md tests/test_docs.py
git commit -m "feat(seeds): idempotent seeder, the seed container role, seeds in the image

Spec 2026-09-06 D7. Upsert by slug (a re-run changes only updated_at); --reset sweeps
source='seed' and never touches source='seller'. Exit codes mirror migrate.py: 2 no
DATABASE_URL, 3 unreachable, 4 bad seed data. ST_MakePoint takes (lng, lat) and a test
reads the point back out of geom rather than trusting the call. seeds/ ships in the
image so the seeder and the photo endpoint both find their data; DEPLOY.md carries the
railway ssh run.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task L5: `GET /api/listings`, `/api/listings/{id}` and `/api/listings/{id}/photos/{n}`

**Files:**
- Create: `app/api/listings.py`
- Modify: `app/main.py` (include the router before the catch-all)
- Create: `tests/api/test_listings.py`
- Create: `tests/perf/conftest.py`
- Modify: `tests/perf/test_api_latency.py`
- Modify: `.github/workflows/quality.yml` (add `--cov=scripts` to the backend coverage run)
- Modify: `tests/test_docs.py` (`REQUIRED_CI_COMMANDS`)

**Interfaces:**
- Consumes: `app.auth.deps.require("listing.read")` and `app.auth.deps.install` (Wave 2a I3/I4); `app.db.sync_conn`; `app.cache.sync_redis`; the `listing` table (L1); the committed photographs (L3); `tests/api/conftest.py`'s `client` and `member`.
- Produces: `app/api/listings.py` exposing `router`, `REQUIRE_LISTING_READ`, `PHOTOS_ROOT`, `LIST_TTL_S = 60`, `DEFAULT_LIMIT = 50`, `MAX_LIMIT = 200`, `relative_listed(listed_at: datetime, now: datetime) -> str`, `encode_cursor(listed_at: datetime, listing_id: UUID) -> str`, `decode_cursor(raw: str) -> tuple[datetime, UUID]`, `serialise(row: Mapping[str, Any], now: datetime) -> dict[str, Any]` (declared and implemented with the same signature — pre-flight M4), `photo_list(value: object) -> list[str]`, `photo_file(photos: list[str], n: int) -> Path | None`. Task L6 consumes the JSON contract below.

### The JSON contract (Task L6 maps exactly these names)

`GET /api/listings?market=<str>&limit=<1..200>&cursor=<opaque>` → `200`

```json
{
  "items": [
    {
      "id": "5f1e…", "slug": "6666_dallas_veterinary_specialist_hospital",
      "name": "6666 Dallas Veterinary Specialist Hospital",
      "market": "Dallas, TX", "area": "Dallas", "type": "Specialty",
      "city": "Dallas", "state": "TX", "street": "17727 Dallas Pkwy, Suite 150", "zip": "75287",
      "phone": "(214) 555-0101", "hours": "Mon–Fri 8 AM–5 PM",
      "price": 2850000, "rev": 4100000, "docs": 6, "rooms": 8, "sqft": 7600, "bldg": "Included",
      "est": 2009, "listed": "6 days ago", "listed_at": "2026-08-31T09:14:00+00:00",
      "status": "published",
      "pop": null, "growth": null, "income": null, "hh": null,
      "note": "Demo listing seeded by the VIN Foundation.",
      "staff": "…", "services": "…", "facility": "…", "ownership": "…",
      "lat": 32.991596, "lng": -96.829738, "location_disclosed": true,
      "photos": ["/api/listings/5f1e…/photos/1", "/api/listings/5f1e…/photos/2"]
    }
  ],
  "next_cursor": null
}
```

`GET /api/listings/{id}` → `200` with one such object (published only).
`GET /api/listings/{id}/photos/{n}` → `200 image/webp`, `Cache-Control: private, max-age=86400`.
Every refusal is decision A5's body — `{"error": {"code": "…", "message": "…"}}` — with `401 UNAUTHORIZED` / "Sign in to continue." for an anonymous caller (raised by `require`, rendered by `deps.install`'s handler), and `404 NOT_FOUND`, `400 BAD_REQUEST` from this module's own helper.

> **`listed` is computed on the server, `listed_at` travels beside it.** The design's card copy is a relative string ("3 days ago", "1 week ago"), and the frontend must not compute it — the pixel gates would then drift with the wall clock. The server renders it from `listed_at` and the frontend copies the string through.

> **`location_disclosed = false` hides the address AND the point.** `street`, `zip`, `lat` and `lng` are `null`; `city`, `state` and `area` remain, because the design's anonymised card shows the area. Every seed sets it true (D8); Wave 2b's sellers default to false, so the branch has to be right now rather than later.

> **The Redis list cache is safe to share across principals.** The list is published-only and carries no per-account field, so every member sees the same bytes; the key is `listings:v1:<market>:<cursor>:<limit>` and the TTL is 60 s. Nothing per-user is ever cached here — if a later task adds a per-account field to this payload, the cache key must gain the account id or the cache must go.

- [ ] **Step 1: Write the failing endpoint tests**

Create `tests/api/test_listings.py`:

```python
"""GET /api/listings, /api/listings/{id} and /api/listings/{id}/photos/{n} (spec D8/D9)."""
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import psycopg2
import pytest

from app.api.listings import (
    LIST_TTL_S,
    decode_cursor,
    encode_cursor,
    photo_file,
    photo_list,
    relative_listed,
    serialise,
)
from tests.api.conftest import auth_headers

INSERT = (
    "INSERT INTO listing (slug, name, street, city, state, zip, phone, hours, status,"
    " location_disclosed, geom, area, type, market, price, rev, docs, rooms, sqft, bldg, est,"
    " listed_at, note, staff, services, facility, ownership, photos, source)"
    " VALUES (%(slug)s,%(name)s,%(street)s,%(city)s,%(state)s,%(zip)s,%(phone)s,%(hours)s,"
    " %(status)s,%(disclosed)s,ST_SetSRID(ST_MakePoint(%(lng)s,%(lat)s),4326)::geography,"
    " %(area)s,'Small animal',%(market)s,1000000,1500000,2,4,3000,'Included',2001,"
    " now() - make_interval(days => %(days)s),'n','s','sv','f','o',%(photos)s::jsonb,'seed')"
    " RETURNING id"
)


def _insert(conn: Any, **over: Any) -> str:
    params: dict[str, Any] = {
        "slug": f"s-{uuid4().hex[:8]}", "name": "Demo Hospital", "street": "1 Main St",
        "city": "Austin", "state": "TX", "zip": "78701", "phone": "(512) 555-0100",
        "hours": "24/7", "status": "published", "disclosed": True, "lat": 30.2672,
        "lng": -97.7431, "area": "Austin", "market": "Austin, TX", "days": 3,
        "photos": json.dumps([]),
    }
    params.update(over)
    with conn.cursor() as cur:
        cur.execute(INSERT, params)
        return str(cur.fetchone()[0])


async def test_anonymous_gets_the_generic_401_body(client: Any, conn: Any, redis: Any) -> None:
    r = await client.get("/api/listings")
    assert r.status_code == 401
    assert r.json() == {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}


async def test_a_member_sees_the_published_listings(client: Any, conn: Any, redis: Any, member: Any) -> None:
    listing_id = _insert(conn)
    _, cookies, headers = member()
    r = await client.get("/api/listings", headers=auth_headers(cookies, headers))
    assert r.status_code == 200
    body = r.json()
    assert [item["id"] for item in body["items"]] == [listing_id]
    assert body["next_cursor"] is None


async def test_unpublished_listings_are_hidden_from_both_endpoints(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    draft = _insert(conn, status="draft")
    _, cookies, headers = member()
    listed = await client.get("/api/listings", headers=auth_headers(cookies, headers))
    assert [item["id"] for item in listed.json()["items"]] == []
    one = await client.get(f"/api/listings/{draft}", headers=auth_headers(cookies, headers))
    assert one.status_code == 404
    assert one.json() == {"error": {"code": "NOT_FOUND", "message": "No such listing."}}


async def test_the_market_filter_narrows_the_list(client: Any, conn: Any, redis: Any, member: Any) -> None:
    austin = _insert(conn, market="Austin, TX")
    _insert(conn, market="Dallas, TX")
    _, cookies, headers = member()
    r = await client.get("/api/listings?market=Austin%2C+TX", headers=auth_headers(cookies, headers))
    assert [item["id"] for item in r.json()["items"]] == [austin]


async def test_pagination_walks_every_row_exactly_once(client: Any, conn: Any, redis: Any, member: Any) -> None:
    ids = {_insert(conn, days=n) for n in range(5)}
    _, cookies, headers = member()
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(5):
        url = "/api/listings?limit=2" + (f"&cursor={cursor}" if cursor else "")
        body = (await client.get(url, headers=auth_headers(cookies, headers))).json()
        seen += [item["id"] for item in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert sorted(seen) == sorted(ids) and len(seen) == len(set(seen))
    assert cursor is None


async def test_a_malformed_cursor_is_a_400_in_the_a5_shape(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    _, cookies, headers = member()
    r = await client.get("/api/listings?cursor=not-a-cursor", headers=auth_headers(cookies, headers))
    assert r.status_code == 400
    assert r.json() == {"error": {"code": "BAD_REQUEST", "message": "Invalid cursor."}}


@pytest.mark.parametrize("bad", ["limit=0", "limit=201", "limit=abc"])
async def test_a_bad_limit_is_a_400_in_the_a5_shape(
    client: Any, conn: Any, redis: Any, member: Any, bad: str
) -> None:
    _, cookies, headers = member()
    r = await client.get(f"/api/listings?{bad}", headers=auth_headers(cookies, headers))
    assert r.status_code == 400
    assert r.json() == {"error": {"code": "BAD_REQUEST", "message": "Invalid limit."}}


async def test_an_undisclosed_listing_returns_no_address_and_no_point(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    listing_id = _insert(conn, disclosed=False)
    _, cookies, headers = member()
    item = (await client.get(f"/api/listings/{listing_id}", headers=auth_headers(cookies, headers))).json()
    assert item["street"] is None and item["zip"] is None
    assert item["lat"] is None and item["lng"] is None
    assert item["city"] == "Austin" and item["state"] == "TX" and item["area"] == "Austin"
    assert item["location_disclosed"] is False


async def test_photos_are_served_as_webp_with_a_private_cache_header(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    listing_id = _insert(conn, photos=json.dumps(["abc_animal_hospital/1.webp"]))
    _, cookies, headers = member()
    r = await client.get(f"/api/listings/{listing_id}/photos/1", headers=auth_headers(cookies, headers))
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"
    assert r.headers["cache-control"] == "private, max-age=86400"
    assert r.content[:4] == b"RIFF" and r.content[8:12] == b"WEBP"


async def test_a_missing_photo_index_is_a_404(client: Any, conn: Any, redis: Any, member: Any) -> None:
    listing_id = _insert(conn, photos=json.dumps(["abc_animal_hospital/1.webp"]))
    _, cookies, headers = member()
    for n in ("0", "2", "99"):
        r = await client.get(f"/api/listings/{listing_id}/photos/{n}", headers=auth_headers(cookies, headers))
        assert r.status_code == 404, n
        assert r.json() == {"error": {"code": "NOT_FOUND", "message": "No such photograph."}}


async def test_photos_are_refused_to_an_anonymous_caller(client: Any, conn: Any, redis: Any) -> None:
    listing_id = _insert(conn, photos=json.dumps(["abc_animal_hospital/1.webp"]))
    r = await client.get(f"/api/listings/{listing_id}/photos/1")
    assert r.status_code == 401


async def test_an_unknown_listing_id_is_a_404_not_a_500(client: Any, conn: Any, redis: Any, member: Any) -> None:
    _, cookies, headers = member()
    for path in (f"/api/listings/{uuid4()}", f"/api/listings/{uuid4()}/photos/1"):
        r = await client.get(path, headers=auth_headers(cookies, headers))
        assert r.status_code == 404, path


async def test_a_non_uuid_listing_id_is_a_404_not_a_500(client: Any, conn: Any, redis: Any, member: Any) -> None:
    _, cookies, headers = member()
    r = await client.get("/api/listings/not-a-uuid", headers=auth_headers(cookies, headers))
    assert r.status_code == 404


async def test_the_list_is_cached_for_sixty_seconds(client: Any, conn: Any, redis: Any, member: Any) -> None:
    _insert(conn)
    _, cookies, headers = member()
    first = await client.get("/api/listings", headers=auth_headers(cookies, headers))
    keys = [k for k in redis.keys("listings:v1:*")]
    assert len(keys) == 1
    assert 0 < redis.ttl(keys[0]) <= LIST_TTL_S
    _insert(conn)  # a row the cached answer cannot know about
    second = await client.get("/api/listings", headers=auth_headers(cookies, headers))
    assert second.json() == first.json(), "the second read must come from the cache"


async def test_a_photo_path_can_never_escape_the_photo_root(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    listing_id = _insert(conn, photos=json.dumps(["../../../../etc/passwd"]))
    _, cookies, headers = member()
    r = await client.get(f"/api/listings/{listing_id}/photos/1", headers=auth_headers(cookies, headers))
    assert r.status_code == 404


async def test_an_over_long_market_is_a_400_in_the_a5_shape(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    """The `len(market) > 64` refusal — no other test sends a long market (pre-flight C2)."""
    _, cookies, headers = member()
    r = await client.get(f"/api/listings?market={'x' * 65}", headers=auth_headers(cookies, headers))
    assert r.status_code == 400
    assert r.json() == {"error": {"code": "BAD_REQUEST", "message": "Invalid market."}}


def _row(**over: Any) -> dict[str, Any]:
    """A `listing` row as `_rows()` builds one, for the direct `serialise` unit tests below."""
    base: dict[str, Any] = {
        "id": uuid4(), "slug": "s", "name": "N", "street": "1 Main St", "city": "Austin",
        "state": "TX", "zip": "78701", "phone": "(512) 555-0100", "hours": "24/7",
        "status": "published", "location_disclosed": True, "lat": 30.2672, "lng": -97.7431,
        "area": "Austin", "type": "Small animal", "market": "Austin, TX", "price": 1,
        "rev": 2, "docs": 3, "rooms": 4, "sqft": 5, "bldg": "Included", "est": 2001,
        "listed_at": datetime(2026, 9, 3, tzinfo=UTC), "note": "n", "staff": "s",
        "services": "sv", "facility": "f", "ownership": "o", "photos": [],
    }
    base.update(over)
    return base


def test_photo_list_accepts_both_a_list_and_a_json_string() -> None:
    """psycopg2 hands `jsonb` back as a list, so the string arm is unreachable from a request
    and must be covered directly (pre-flight C2)."""
    assert photo_list(["a/1.webp"]) == ["a/1.webp"]
    assert photo_list('["a/1.webp", "a/2.webp"]') == ["a/1.webp", "a/2.webp"]
    assert photo_list([]) == []
    assert photo_list(None) == []


def test_serialise_handles_photos_arriving_as_a_json_string() -> None:
    now = datetime(2026, 9, 6, tzinfo=UTC)
    body = serialise(_row(photos='["abc_animal_hospital/1.webp"]'), now)
    assert body["photos"] == [f"/api/listings/{body['id']}/photos/1"]


def test_serialise_omits_a_point_a_disclosed_listing_never_had() -> None:
    """`disclosed and lat is not None` — the combination `disclosed=True, geom NULL`. Every
    inserted row in this file has a point, so this arm is only reachable directly. A seller's
    listing in Wave 2b will be exactly this shape before it is geocoded (pre-flight C2)."""
    body = serialise(_row(lat=None, lng=None), datetime(2026, 9, 6, tzinfo=UTC))
    assert body["lat"] is None and body["lng"] is None
    assert body["location_disclosed"] is True
    assert body["street"] == "1 Main St"


def test_serialise_blanks_the_address_of_an_undisclosed_listing() -> None:
    body = serialise(_row(location_disclosed=False), datetime(2026, 9, 6, tzinfo=UTC))
    assert (body["street"], body["zip"], body["lat"], body["lng"]) == (None, None, None, None)
    assert (body["city"], body["state"], body["area"]) == ("Austin", "TX", "Austin")


def test_photo_file_refuses_an_escaping_path() -> None:
    assert photo_file(["../../etc/passwd"], 1) is None
    assert photo_file([], 1) is None
    assert photo_file(["abc_animal_hospital/1.webp"], 0) is None
    assert photo_file(["abc_animal_hospital/1.webp"], 2) is None
    assert photo_file(["abc_animal_hospital/nope.webp"], 1) is None


@pytest.mark.parametrize(
    "days, expected",
    [(0, "today"), (1, "1 day ago"), (2, "2 days ago"), (6, "6 days ago"), (7, "1 week ago"),
     (13, "1 week ago"), (14, "2 weeks ago"), (20, "2 weeks ago"), (21, "3 weeks ago"),
     (27, "3 weeks ago"), (28, "1 month ago"), (59, "1 month ago"), (60, "2 months ago"),
     (120, "4 months ago")],
)
def test_relative_listed_matches_the_designs_vocabulary(days: int, expected: str) -> None:
    now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    assert relative_listed(now - timedelta(days=days, hours=1), now) == expected


def test_cursors_round_trip_and_reject_rubbish() -> None:
    at = datetime(2026, 9, 1, 8, 30, tzinfo=UTC)
    listing_id = uuid4()
    assert decode_cursor(encode_cursor(at, listing_id)) == (at, listing_id)
    for rubbish in ("", "!!!", "YWJj", "MjAyNi0wOS0wMXxub3QtYS11dWlk"):
        with pytest.raises(ValueError):
            decode_cursor(rubbish)


def test_the_listings_routes_are_guarded_not_public(dist: Any) -> None:
    """Global Constraint (e): three new routes, nothing added to PUBLIC_ROUTES."""
    from app.auth import permissions as PM
    from app.main import create_app

    paths = {p for _, p in PM.PUBLIC_ROUTES}
    assert not any(p.startswith("/api/listings") for p in paths)
    app = create_app(dist=dist)
    mounted = {route.path for route in app.routes if hasattr(route, "path")}
    assert "/api/listings" in mounted


async def test_a_seeded_database_serves_all_eighteen(client: Any, conn: Any, redis: Any, member: Any) -> None:
    """The end-to-end shape: the real seeder, the real endpoint, the real photograph files.

    `conn` monkeypatches `settings.database_url` to the scratch database, so the seeder writes
    to the same database this request reads."""
    from app.config import settings
    from scripts import seed_listings as SL

    SL.seed(settings.database_url, reset=True)
    _, cookies, headers = member()
    r = await client.get("/api/listings?limit=200", headers=auth_headers(cookies, headers))
    items = r.json()["items"]
    assert len(items) == 18
    assert all(item["photos"] for item in items)
    assert all(item["lat"] is not None and item["lng"] is not None for item in items)
    assert {item["market"] for item in items} >= {"Dallas, TX", "Austin, TX", "Atlanta, GA"}


async def test_a_photograph_of_a_seeded_hospital_is_really_served(
    client: Any, conn: Any, redis: Any, member: Any
) -> None:
    from app.config import settings
    from scripts import seed_listings as SL

    SL.seed(settings.database_url, reset=True)
    _, cookies, headers = member()
    auth = auth_headers(cookies, headers)
    items = (await client.get("/api/listings?limit=200", headers=auth)).json()["items"]
    first = items[0]
    photo = await client.get(first["photos"][0], headers=auth)
    assert photo.status_code == 200 and photo.content[:4] == b"RIFF"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `poetry run pytest tests/api/test_listings.py -v`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'app.api.listings'`.

- [ ] **Step 3: Write the endpoints**

Create `app/api/listings.py`:

```python
"""The listing read surface (spec 2026-09-06, D8).

Three routes, all guarded by `listing.read`: the paginated published list, one listing, and one
photograph. An anonymous caller gets the identity design's generic 401 and the frontend shows
the sign-in gate.

Shapes that are load-bearing:

* **`require(...)` is hoisted to ONE module-level constant** and used through `Depends`. The
  route-guard and audit drift tests resolve a route's permission by the guard's object
  IDENTITY (`app.auth.deps.permission_of`), so a wrapper would read as unguarded.
* **Refusals this module raises use `_error(...)`, which writes decision A5's body directly.**
  Everything `require` raises is an `AuthError` and is rendered by the one handler
  `deps.install(app)` registered. This module never raises a bare `HTTPException`, whose body
  would be `{"detail": ...}`; and it parses `limit`/`cursor` by hand rather than through
  `Query(ge=…, le=…)`, so a bad value gets the same `{"error": {...}}` envelope as everything
  else instead of FastAPI's `{"detail": [...]}`.
* **Connections are opened with `closing(sync_conn()) as conn, conn`,** exactly as
  `app.api.auth` does: psycopg2's own `with conn:` is the TRANSACTION manager and commits
  WITHOUT closing, so `with sync_conn() as conn:` alone leaks a connection per request.
* **`listing.read` is not in `permissions.AUDITED`,** so no handler here writes an audit row;
  `tests/auth/test_permissions.py::test_audited_permissions_are_written_by_their_handlers`
  keeps that honest rather than assumed.
"""
from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.auth.deps import require
from app.cache import sync_redis
from app.db import sync_conn

router = APIRouter(prefix="/api")

# Hoisted to a module-level constant, never wrapped (Global Constraint (g)).
REQUIRE_LISTING_READ = require("listing.read")

ROOT = Path(__file__).resolve().parent.parent.parent
PHOTOS_ROOT = ROOT / "seeds" / "hospitals" / "photos"
LIST_TTL_S = 60
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
PHOTO_CACHE_CONTROL = "private, max-age=86400"

_SELECT = """
SELECT id, slug, name, street, city, state, zip, phone, hours, status, location_disclosed,
       ST_Y(geom::geometry) AS lat, ST_X(geom::geometry) AS lng,
       area, type, market, price, rev, docs, rooms, sqft, bldg, est, listed_at,
       note, staff, services, facility, ownership, photos
  FROM listing
"""
_COLUMNS = (
    "id", "slug", "name", "street", "city", "state", "zip", "phone", "hours", "status",
    "location_disclosed", "lat", "lng", "area", "type", "market", "price", "rev", "docs",
    "rooms", "sqft", "bldg", "est", "listed_at", "note", "staff", "services", "facility",
    "ownership", "photos",
)


def _error(code: str, message: str, status: int) -> JSONResponse:
    """Decision A5's body for the refusals this module raises itself."""
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def relative_listed(listed_at: datetime, now: datetime) -> str:
    """The design's own vocabulary for a card's "listed" line, rendered on the SERVER so the
    pixel gates never drift with the wall clock (the frontend copies the string through)."""
    days = (now - listed_at).days
    if days < 1:
        return "today"
    if days == 1:
        return "1 day ago"
    if days < 7:
        return f"{days} days ago"
    if days < 28:
        weeks = days // 7
        return "1 week ago" if weeks == 1 else f"{weeks} weeks ago"
    months = max(1, days // 30)
    return "1 month ago" if months == 1 else f"{months} months ago"


def encode_cursor(listed_at: datetime, listing_id: UUID) -> str:
    raw = f"{listed_at.isoformat()}|{listing_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(raw: str) -> tuple[datetime, UUID]:
    """The (listed_at, id) keyset a cursor names. Raises ValueError for anything else."""
    padded = raw + "=" * (-len(raw) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode()).decode()
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("bad cursor") from exc
    at, _, listing_id = decoded.partition("|")
    return datetime.fromisoformat(at), UUID(listing_id)


def photo_list(value: object) -> list[str]:
    """`listing.photos` as a list of relative paths.

    psycopg2 decodes a `jsonb` column to a Python list, so the string arm is unreachable from a
    request — but `serialise` is also called directly (by tests, and by Wave 2b's admin views,
    which read rows through other drivers), and 100 % branches is the gate. One helper with two
    tested arms, rather than the same defensive ternary written twice (pre-flight C2)."""
    if isinstance(value, str):
        loaded = json.loads(value)
        return [str(item) for item in loaded]
    return [str(item) for item in (value or [])]


def photo_file(photos: list[str], n: int) -> Path | None:
    """The file behind photo `n` (1-based) of `photos`, or None. The path comes from the
    database, so it is resolved under PHOTOS_ROOT and anything that escapes is refused —
    a `photos` value of `["../../../etc/passwd"]` must be a 404, not a file read."""
    if not 1 <= n <= len(photos):
        return None
    root = PHOTOS_ROOT.resolve()
    candidate = (root / photos[n - 1]).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate


def serialise(row: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    """One database row as the JSON contract Task L6 maps. `location_disclosed=false` blanks
    the street, the postcode and the point; the city, state and area stay (the design's
    anonymised card shows the area)."""
    disclosed = bool(row["location_disclosed"])
    listing_id = str(row["id"])
    photos = photo_list(row["photos"])
    return {
        "id": listing_id, "slug": row["slug"], "name": row["name"],
        "market": row["market"], "area": row["area"], "type": row["type"],
        "city": row["city"], "state": row["state"],
        "street": row["street"] if disclosed else None,
        "zip": row["zip"] if disclosed else None,
        "phone": row["phone"], "hours": row["hours"],
        "price": row["price"], "rev": row["rev"], "docs": row["docs"], "rooms": row["rooms"],
        "sqft": row["sqft"], "bldg": row["bldg"], "est": row["est"],
        "listed": relative_listed(row["listed_at"], now),
        "listed_at": row["listed_at"].isoformat(),
        "status": row["status"],
        # D4: the community figures stay null until the Census plan supplies them; the UI
        # shows its existing empty state for them.
        "pop": None, "growth": None, "income": None, "hh": None,
        "note": row["note"], "staff": row["staff"], "services": row["services"],
        "facility": row["facility"], "ownership": row["ownership"],
        "lat": float(row["lat"]) if disclosed and row["lat"] is not None else None,
        "lng": float(row["lng"]) if disclosed and row["lng"] is not None else None,
        "location_disclosed": disclosed,
        "photos": [f"/api/listings/{listing_id}/photos/{n}" for n in range(1, len(photos) + 1)],
    }


def _rows(conn: Any, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [dict(zip(_COLUMNS, row, strict=True)) for row in cur.fetchall()]


def _parse_limit(raw: str | None) -> int | None:
    if raw is None:
        return DEFAULT_LIMIT
    if not raw.isdecimal():
        return None
    value = int(raw)
    return value if 1 <= value <= MAX_LIMIT else None


@router.get("/listings", dependencies=[Depends(REQUIRE_LISTING_READ)])
async def list_listings(request: Request) -> Response:
    limit = _parse_limit(request.query_params.get("limit"))
    if limit is None:
        return _error("BAD_REQUEST", "Invalid limit.", 400)
    market = request.query_params.get("market")
    if market is not None and len(market) > 64:
        return _error("BAD_REQUEST", "Invalid market.", 400)
    raw_cursor = request.query_params.get("cursor")
    keyset: tuple[datetime, UUID] | None = None
    if raw_cursor is not None:
        try:
            keyset = decode_cursor(raw_cursor)
        except ValueError:
            return _error("BAD_REQUEST", "Invalid cursor.", 400)

    cache_key = f"listings:v1:{market or ''}:{raw_cursor or ''}:{limit}"
    redis_ = sync_redis()
    cached = redis_.get(cache_key)
    if cached is not None:
        return Response(content=cached, media_type="application/json")

    where = ["status = 'published'"]
    params: list[Any] = []
    if market is not None:
        where.append("market = %s")
        params.append(market)
    if keyset is not None:
        where.append("(listed_at, id) < (%s, %s)")
        params += [keyset[0], keyset[1]]
    sql = f"{_SELECT} WHERE {' AND '.join(where)} ORDER BY listed_at DESC, id DESC LIMIT %s"
    params.append(limit + 1)  # one extra row tells us whether another page exists

    with closing(sync_conn()) as conn, conn:
        rows = _rows(conn, sql, tuple(params))
    now = datetime.now(UTC)
    page, more = rows[:limit], len(rows) > limit
    body = {
        "items": [serialise(row, now) for row in page],
        "next_cursor": encode_cursor(page[-1]["listed_at"], UUID(str(page[-1]["id"]))) if more else None,
    }
    payload = json.dumps(body)
    redis_.setex(cache_key, LIST_TTL_S, payload)
    return Response(content=payload, media_type="application/json")


def _published(conn: Any, listing_id: str) -> dict[str, Any] | None:
    try:
        parsed = UUID(listing_id)
    except ValueError:
        return None
    rows = _rows(conn, f"{_SELECT} WHERE id = %s AND status = 'published'", (parsed,))
    return rows[0] if rows else None


@router.get("/listings/{listing_id}", dependencies=[Depends(REQUIRE_LISTING_READ)])
async def get_listing(listing_id: str) -> Response:
    with closing(sync_conn()) as conn, conn:
        row = _published(conn, listing_id)
    if row is None:
        return _error("NOT_FOUND", "No such listing.", 404)
    return JSONResponse(serialise(row, datetime.now(UTC)))


@router.get("/listings/{listing_id}/photos/{n}", dependencies=[Depends(REQUIRE_LISTING_READ)])
async def get_listing_photo(listing_id: str, n: int) -> Response:
    with closing(sync_conn()) as conn, conn:
        row = _published(conn, listing_id)
    if row is None:
        return _error("NOT_FOUND", "No such listing.", 404)
    path = photo_file(photo_list(row["photos"]), n)
    if path is None:
        return _error("NOT_FOUND", "No such photograph.", 404)
    return Response(
        content=path.read_bytes(),
        media_type="image/webp",
        headers={"Cache-Control": PHOTO_CACHE_CONTROL},
    )
```

In `app/main.py`, include the router with the other `/api` routers — **before** `not_found_router`, which is the catch-all:

```python
from app.api.listings import router as listings_router
...
    app.include_router(auth_router)
    app.include_router(interest_router)
    app.include_router(listings_router)
    app.include_router(not_found_router)
```

- [ ] **Step 4: Run the endpoint tests to verify they pass**

Run: `poetry run pytest tests/api/test_listings.py -v`
Expected: PASS. Then the guard walk, which must still be clean:

Run: `poetry run pytest tests/auth/test_permissions.py -v`
Expected: PASS — `_unguarded`, `_unresolvable` and `_unaudited` are all empty with three new routes mounted and **nothing added to `PUBLIC_ROUTES`**.

- [ ] **Step 5: Write the failing perf budgets**

Create `tests/perf/conftest.py`:

```python
"""Fixtures the listings budgets need.

`member` is imported from tests/api/conftest.py rather than re-implemented, and `client` is
DELIBERATELY not imported: the root conftest's `client` (a tmp_path `dist`, base URL
http://test) is what the existing `/api/healthz` and `/` budgets measure, and shadowing it
here would silently change what those two tests are timing. The listings budgets build their
own client against the site's real origin instead.
"""
import httpx
import pytest
from httpx import ASGITransport

from app.main import create_app
from tests.api.conftest import ORIGIN, member

__all__ = ["ORIGIN", "member", "origin_client"]


@pytest.fixture
async def origin_client(redis):
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app()), base_url=ORIGIN) as c:
        yield c
```

Append to `tests/perf/test_api_latency.py`:

```python
# Listings budgets (policy §3; spec 2026-09-06 D9). They live here as their own tests rather
# than in BUDGET_MS because they need a signed-in member — exactly as the interest POST budget
# above does. The list is Redis-cached for 60 s, so this measures the warm path, which is the
# path a member actually experiences.
LISTINGS_BUDGET_MS = {"list": 100, "one": 100, "photo": 150}


async def test_listings_p95_within_budget(origin_client, conn, redis, member):
    from scripts import seed_listings as SL
    from tests.api.conftest import auth_headers

    SL.seed(settings.database_url, reset=True)
    _, cookies, headers = member()
    auth = auth_headers(cookies, headers)

    listed = await origin_client.get("/api/listings?limit=200", headers=auth)
    assert listed.status_code == 200, listed.text
    first = listed.json()["items"][0]

    async def timed(path: str) -> float:
        await origin_client.get(path, headers=auth)  # warm-up
        samples = []
        for _ in range(50):
            t0 = time.perf_counter()
            r = await origin_client.get(path, headers=auth)
            samples.append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200, path
        return statistics.quantiles(samples, n=20)[18]

    assert await timed("/api/listings?limit=200") <= LISTINGS_BUDGET_MS["list"], "/api/listings p95 over 100 ms"
    assert await timed(f"/api/listings/{first['id']}") <= LISTINGS_BUDGET_MS["one"], "/api/listings/{id} p95 over 100 ms"
    assert await timed(f"/api/listings/{first['id']}/photos/1") <= LISTINGS_BUDGET_MS["photo"], "photo p95 over 150 ms"
```

Run: `poetry run pytest tests/perf/test_api_latency.py -v`
Expected: PASS. If a budget is missed, **do not raise the number** — profile it. The likely cause is the list query missing `listing_page_idx`; confirm with

```bash
poetry run python - <<'PY'
import psycopg2, os
sql = ("EXPLAIN (FORMAT JSON) SELECT id FROM listing WHERE status='published'"
       " ORDER BY listed_at DESC, id DESC LIMIT 51")
with psycopg2.connect(os.environ["DATABASE_URL"]) as c, c.cursor() as cur:
    cur.execute(sql); print(cur.fetchone()[0][0]["Plan"]["Node Type"])
PY
```

- [ ] **Step 6: Run the full gate**

```bash
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
```
Expected: all green at 100 % lines and branches.

Every arm of `app/api/listings.py` that no *request* can reach has a named test in Step 1 rather than being left to improvisation (pre-flight C2 — a plan may not defer coverage): the `market` length refusal (`test_an_over_long_market_is_a_400_in_the_a5_shape`), `photo_list`'s string arm (`test_photo_list_accepts_both_a_list_and_a_json_string`, `test_serialise_handles_photos_arriving_as_a_json_string`), and the `disclosed and lat is None` combination (`test_serialise_omits_a_point_a_disclosed_listing_never_had`). If coverage still reports an uncovered arm, **write the test for it in this task** — do not widen the scope and do not add a suppression (Global Constraint (c)).

- [ ] **Step 6b: Put `scripts/` under the CI coverage gate (RED → GREEN)**

Global Constraint (a) claims CI plus `diff-cover` holds the new modules to 100 %. It does not, yet: `.github/workflows/quality.yml:64` runs `--cov=app` only, so `coverage.xml` contains no `scripts/*.py` rows and `diff-cover` has nothing to compare (pre-flight I6). `tests/test_docs.py::REQUIRED_CI_COMMANDS` is the drift test that makes the workflow and this plan agree.

In `tests/test_docs.py`, add one entry to `REQUIRED_CI_COMMANDS`, immediately after `"--cov=app",`:

```python
    "--cov=app",
    "--cov=scripts",   # seed listings: scripts/prepare_photos.py and scripts/seed_listings.py
```

Run: `poetry run pytest tests/test_docs.py -v`
Expected: FAIL — the workflow does not contain `--cov=scripts`.

In `.github/workflows/quality.yml`, extend the backend coverage run (line 64):

```yaml
      - run: poetry run pytest -q -W error --cov=app --cov=scripts --cov-report=xml --cov-fail-under=90
```

> The `--cov-fail-under` number is **not** changed here. Raising the repository-wide floor is a separate decision with its own blast radius; what this plan needs is for `scripts/` to appear in `coverage.xml` so `diff-cover … --fail-under=100` enforces every changed line of the two new modules on every PR. The 100 % lines-and-branches gate stays as the plan's own per-task command.

Run: `poetry run pytest tests/test_docs.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd "/Users/johndean/Development/Practice Match"
git add app/api/listings.py app/main.py tests/api/test_listings.py \
        tests/perf/conftest.py tests/perf/test_api_latency.py \
        .github/workflows/quality.yml tests/test_docs.py
git commit -m "feat(api): listings read surface behind listing.read

Spec 2026-09-06 D8. GET /api/listings (published only, ?market=, keyset cursor,
Redis-cached 60 s), GET /api/listings/{id} and GET /api/listings/{id}/photos/{n}
(WebP, private cache). require(\"listing.read\") is one hoisted module constant so the
route-guard drift test can read it; nothing is added to PUBLIC_ROUTES. Every refusal
uses decision A5's body, limit and cursor are parsed by hand so a bad value is not
FastAPI's detail envelope, location_disclosed=false blanks street, zip and the point,
and a photo path from the database can never escape seeds/hospitals/photos.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task L6: The frontend reads listings from the API, keeping every field name

**Files:**
- Create: `frontend/src/listings/load.ts`
- Create: `frontend/src/listings/load.test.ts`
- Create: `frontend/tests/design-listings.mjs`
- Modify: `frontend/src/logic.js` (the footer export only)
- Modify: `frontend/tests/app-generated.test.ts` (the port drift test's `FOOTER`)
- Modify: `frontend/src/main.ts`
- Modify: `frontend/src/main.test.ts`
- Modify: `frontend/tests/harness.ts` (`prepare()` serves the design-fixture stub)

**Interfaces:**
- Consumes: the JSON contract from Task L5; `frontend/src/logic.js`'s fixture arrays; `frontend/tests/harness.ts`'s `prepare(page)`; `frontend/tests/screens.ts`'s 27 V3 states; `frontend/tests/baseline-manifest.test.ts`.
- Produces: `frontend/src/listings/load.ts` exporting `MARKET_ZOOM = 10`, `US_CENTER`, `LOAD_TIMEOUT_MS = 5000`, `type ApiListing`, `type Practice`, `type Markets`, `type ListingsPage`, `toPractice(row: ApiListing): Practice`, `centroid(practices: Practice[], market: string): [number, number]`, `applyListings(rows: ApiListing[], practices: Practice[], markets: Markets): void`, `loadListings(fetchFn: typeof fetch, practices: Practice[], markets: Markets, url?: string): Promise<boolean>`. `frontend/src/logic.js` exports `{ Component, MARKETS, P }`. `frontend/tests/design-listings.mjs` exports `toApiShape(practice, index)` and `designListingsBody()`.

> **→ John (pre-flight I11) — `phone` and `street` are stored and served, but reach no screen.** `toPractice` deliberately drops `slug` (it becomes `id`), `street`, `city`, `state`, `zip`, `phone`, `listed_at` and `location_disclosed`, because the design's practice objects carry no field for any of them — adding one would put a key in `P` that the template never reads and that the design-fixture round trip would then have to account for. Spec §1 tells the member they will see each hospital "at a real, mapable street address with a fake `555` phone number, opening hours and photographs": of those four, **the map pin and `hours` are honoured; the printed address and the phone number are not.** The default applied here is to store and serve them anyway — Wave 2b's seller and admin views need them, and the Census geocode joins on them — and to say so plainly in the L7 hand-back so John does not go looking for the phone numbers he supplied. Showing them is a design change, in the same family as the title/photo question below.

> **How the arrays are reached without restructuring `logic.js`.** `logic.js` is the design file's own `<script data-dc-script>` block with exactly three documented edits: the provenance header plus the `DCLogic` import, the asset-path rewrite, and the trailing `export { Component };`. This task changes **only the trailing export**, to `export { Component, MARKETS, P };` — the same accepted edit point, one line, with the ported body byte-identical. `load.ts` then mutates those two objects **in place** (`P.length = 0; P.push(...)`), so every reader inside `logic.js` — `renderVals()`, `photoSet`, `marketPanel` — sees the new data through the same binding it always used. Nothing is restructured, no method is monkeypatched, no prototype is touched.

> **Why the design's four market centres are preserved, not recomputed.** `MARKETS["Austin, TX"].center` is `[30.31, -97.75]` in the design; the centroid of the nine Austin fixtures is about `[30.36, -97.77]`. Recomputing it would pan the map a few pixels and fail the zero-tolerance visual gate for a reason that has nothing to do with this change. So `applyListings` **keeps an existing market's `center`/`zoom` untouched** and derives one only for a market `MARKETS` does not already know; a market with no remaining listings is dropped so the metro selector never offers an empty one.

> ### ⚠️ STOP — the design does not read `p.name` or `p.photos`, and this is John's call
>
> **This is confirmed, not suspected** (pre-flight I1, which corrected an earlier draft of this note on both scope and mechanism). `grep` for `p.name` and `p.photos` in `docs/design-reference/design_handoff_practice_match_v3/Practice Match V3.dc.html` returns **0 matches each**, and the same is true of `frontend/src/logic.js` on `main`. There are **five** sites, not two — the plan's earlier note undercounted them, and `thumbSrc` is new in V3 and exists nowhere on `main`:
>
> | # | Site (V3 design file) | What it does today |
> |---|---|---|
> | 1 | `practiceName` | `return NAMES[p.id] \|\| p.area + " Veterinary";` — a fixture map keyed by the design's own ids |
> | 2 | `photoSet`, the `p.id === "p2"` branch | `src: SRC[id] \|\| ""`, where `SRC` is keyed by **slot id** (`"ph-" + p.id + "-" + view`) and the whole branch is gated on `p.id === "p2"` |
> | 3 | `photoSet`, the generic branch | `src: "", hasSrc: false, noSrc: true` — every non-`p2` practice gets empty slots by construction |
> | 4 | `heroSrc` | `return p.id === "p2" ? "assets/photos/round-rock-exterior-street.webp" : "";` |
> | 5 | `thumbSrc` (**V3 only**) | same shape as `heroSrc`, with the parking photograph |
>
> So **D5's title slot and D3's photo slots are both unreachable from listing data** until something changes. Three options, and the recommendation is not the one the earlier draft of this plan assumed:
>
> **(i) A hand edit to `frontend/src/logic.js` — REJECT.** It is five sites, not one line. Worse, it *cannot pass Browse V3's own drift test*: `frontend/tests/app-generated.test.ts` asserts `logic.js === HEADER + designBody.replace(/"assets\//g, '"/assets/') + FOOTER`, byte for byte. Any hand edit to the body fails it, so taking this option means weakening the gate V3 just built — and it violates CLAUDE.md's "ported files are byte-identical except the edits listed in the platform spec §3" without a §3 amendment. It would also be silently lost at the next re-port.
>
> **(ii) Named rewrite rules in the port transform, each unit-tested — VIABLE FALLBACK.** Note that `frontend/scripts/convert-dc.mjs` has **no `logic.js` transform at all** (its single `assets/` rewrite is inside `element()`'s static-attribute path and applies to HTML attributes only). The `logic.js` rewrite lives in Browse V3's hand-run port step and in the drift test's own `body` computation. Adding five named `String.replace` rules there keeps "never hand-edit `logic.js`" literally true, keeps the drift test byte-exact, and survives a V4 re-port automatically. Cost: five brittle string rewrites over JS source, plus a platform-spec §3 amendment listing them.
>
> **(iii) Change the design file so the script reads `p.name` / `p.photos`, re-issued as V3.1 — RECOMMENDED.** The design file is the declared source of truth; edit it there and the port stays verbatim with its existing three documented edits, the drift test recomputes `body` from the new file and passes unchanged, and no §3 amendment is needed. It is **pixel-safe**: the design's own `P` carries no `name` and no `photos`, so both fallbacks fire and the reference baselines — generated from the design HTML itself — do not move. Cost: John re-opens the canvas and re-issues the handoff, and `frontend/tests/design-source.test.ts` plus the `gen:app` path take a version bump. Normal handoff hygiene, not new machinery.
>
> The minimum edit set under (ii) or (iii) is: `practiceName` → `p.name || NAMES[p.id] || p.area + " Veterinary"`; `photoSet` (both branches) → `src: SRC[id] || (p.photos && p.photos[i]) || ""` with matching `hasSrc`/`noSrc`; `heroSrc` and `thumbSrc` → `(p.photos && p.photos[0]) || <the existing p2 expression>`. Putting `p.name` **first** is pixel-safe precisely because `toPractice` omits `name` when the API sends `null`, which is exactly what the design-fixture stub sends.
>
> **This task does not choose.** `load.ts`, the API and the seeds all carry `name` and `photos` either way, so whichever John picks is a small, self-contained follow-up. **Do not implement any of the three here.** Related and also John's: the caption question in Task L3 (the design has six fixed captioned slots; the seeds supply at most four photographs in filename order).

- [ ] **Step 0: Probe the merged V3 `logic.js` for the two readers**

```bash
cd "/Users/johndean/Development/Practice Match/frontend"
grep -n 'NAMES\[p\.id\]' src/logic.js            # expect 1 hit — the fixture-map title lookup
grep -n 'heroSrc\|thumbSrc\|const SRC' src/logic.js  # expect 3-4 hits — the photo resolvers
grep -c 'p\.photos' src/logic.js                  # expect 0 — 0 means the STOP above is live
```

> A bare `grep -n 'p\.name\|\.photos'` is **not** the probe to use: it also matches the seller wizard's own draft counter (`w.photos`, a number, read while building the upload list), which reads as a false positive and would let an implementer conclude the design already supports this (pre-flight M5). The three greps above match only the five sites the STOP note enumerates.

Record what you find in the hand-back note (Task L7). If `p.photos` has 0 hits and `NAMES[p.id]` has 1, raise the STOP above **now**, before writing code — the rest of this task is unaffected either way, but John's answer changes what QA will show.

- [ ] **Step 1: Write the failing loader test**

Create `frontend/src/listings/load.test.ts`:

```ts
import { describe, expect, it, vi } from 'vitest';
import { applyListings, centroid, LOAD_TIMEOUT_MS, loadListings, MARKET_ZOOM, toPractice, US_CENTER } from './load';
import type { ApiListing, Markets, Practice } from './load';

function row(over: Partial<ApiListing> = {}): ApiListing {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    slug: 'p1',
    name: null,
    market: 'Austin, TX',
    area: 'Cedar Park',
    type: 'Small animal',
    city: 'Cedar Park',
    state: 'TX',
    street: '1 Main St',
    zip: '78613',
    phone: '(512) 555-0100',
    hours: 'Mon–Fri 7:30–6',
    price: 1450000,
    rev: 2100000,
    docs: 3,
    rooms: 5,
    sqft: 4200,
    bldg: 'Included',
    est: 1998,
    listed: '3 days ago',
    listed_at: '2026-09-03T00:00:00+00:00',
    status: 'published',
    pop: null,
    growth: null,
    income: null,
    hh: null,
    note: 'Demo listing seeded by the VIN Foundation.',
    staff: '3 DVMs',
    services: 'Wellness',
    facility: 'Freestanding building',
    ownership: 'Sole proprietor',
    lat: 30.5052,
    lng: -97.8203,
    location_disclosed: true,
    photos: [],
    ...over
  };
}

describe('toPractice', () => {
  it('maps every field the design template reads, under the design’s own names', () => {
    expect(toPractice(row())).toEqual({
      id: 'p1',
      area: 'Cedar Park',
      type: 'Small animal',
      price: 1450000,
      rev: 2100000,
      docs: 3,
      rooms: 5,
      sqft: 4200,
      bldg: 'Included',
      lat: 30.5052,
      lng: -97.8203,
      est: 1998,
      listed: '3 days ago',
      status: 'published',
      pop: null,
      growth: null,
      income: null,
      hh: null,
      note: 'Demo listing seeded by the VIN Foundation.',
      staff: '3 DVMs',
      hours: 'Mon–Fri 7:30–6',
      services: 'Wellness',
      facility: 'Freestanding building',
      ownership: 'Sole proprietor',
      market: 'Austin, TX'
    });
  });

  it('adds `name` only when the API sends one', () => {
    expect('name' in toPractice(row())).toBe(false);
    expect(toPractice(row({ name: 'ABC Animal Hospital' })).name).toBe('ABC Animal Hospital');
  });

  it('adds `photos` only when there is at least one', () => {
    expect('photos' in toPractice(row())).toBe(false);
    expect(toPractice(row({ photos: ['/api/listings/x/photos/1'] })).photos).toEqual(['/api/listings/x/photos/1']);
  });

  it('carries a withheld location through as null rather than inventing a point', () => {
    const p = toPractice(row({ location_disclosed: false, lat: null, lng: null }));
    expect(p.lat).toBeNull();
    expect(p.lng).toBeNull();
  });
});

describe('centroid', () => {
  it('averages the located practices of one market', () => {
    const practices = [
      toPractice(row({ slug: 'a', market: 'M', lat: 10, lng: 20 })),
      toPractice(row({ slug: 'b', market: 'M', lat: 20, lng: 40 })),
      toPractice(row({ slug: 'c', market: 'other', lat: 90, lng: 90 }))
    ];
    expect(centroid(practices, 'M')).toEqual([15, 30]);
  });

  it('ignores practices whose location is withheld', () => {
    const practices = [
      toPractice(row({ slug: 'a', market: 'M', lat: 10, lng: 20 })),
      toPractice(row({ slug: 'b', market: 'M', location_disclosed: false, lat: null, lng: null }))
    ];
    expect(centroid(practices, 'M')).toEqual([10, 20]);
  });

  it('falls back to the centre of the United States when nothing in the market is located', () => {
    const practices = [toPractice(row({ slug: 'a', market: 'M', location_disclosed: false, lat: null, lng: null }))];
    expect(centroid(practices, 'M')).toEqual(US_CENTER);
  });
});

describe('applyListings', () => {
  it('replaces the fixture practices in place, so every reader inside logic.js sees them', () => {
    const practices: Practice[] = [toPractice(row({ slug: 'old' }))];
    const original = practices;
    applyListings([row({ slug: 'new' })], practices, { 'Austin, TX': { center: [30.31, -97.75], zoom: 10 } });
    expect(practices).toBe(original);
    expect(practices.map((p) => p.id)).toEqual(['new']);
  });

  it('keeps a known market’s centre and zoom exactly as the design set them', () => {
    const markets: Markets = { 'Austin, TX': { center: [30.31, -97.75], zoom: 10 } };
    applyListings([row({ lat: 40, lng: -80 })], [], markets);
    expect(markets['Austin, TX']).toEqual({ center: [30.31, -97.75], zoom: 10 });
  });

  it('derives a centre for a market the design does not know', () => {
    const markets: Markets = { 'Austin, TX': { center: [30.31, -97.75], zoom: 10 } };
    applyListings(
      [row({ slug: 'd1', market: 'Dallas, TX', lat: 32.99, lng: -96.83 }), row({ slug: 'a1' })],
      [],
      markets
    );
    expect(markets['Dallas, TX']).toEqual({ center: [32.99, -96.83], zoom: MARKET_ZOOM });
  });

  it('drops a market that no longer has a listing', () => {
    const markets: Markets = {
      'Austin, TX': { center: [30.31, -97.75], zoom: 10 },
      'Orlando, FL': { center: [28.52, -81.36], zoom: 10 }
    };
    applyListings([row()], [], markets);
    expect(Object.keys(markets)).toEqual(['Austin, TX']);
  });
});

describe('loadListings', () => {
  const ok = (items: ApiListing[]) =>
    vi.fn(async () => new Response(JSON.stringify({ items, next_cursor: null }), {
      status: 200,
      headers: { 'content-type': 'application/json' }
    })) as unknown as typeof fetch;

  it('replaces the fixtures on a 200 and reports that it did', async () => {
    const practices: Practice[] = [toPractice(row({ slug: 'fixture' }))];
    const markets: Markets = { 'Austin, TX': { center: [30.31, -97.75], zoom: 10 } };
    await expect(loadListings(ok([row({ slug: 'seeded' })]), practices, markets)).resolves.toBe(true);
    expect(practices.map((p) => p.id)).toEqual(['seeded']);
  });

  it('leaves the fixtures alone when the API refuses (the signed-out gate)', async () => {
    const practices: Practice[] = [toPractice(row({ slug: 'fixture' }))];
    const markets: Markets = { 'Austin, TX': { center: [30.31, -97.75], zoom: 10 } };
    const refused = vi.fn(async () => new Response('', { status: 401 })) as unknown as typeof fetch;
    await expect(loadListings(refused, practices, markets)).resolves.toBe(false);
    expect(practices.map((p) => p.id)).toEqual(['fixture']);
    expect(Object.keys(markets)).toEqual(['Austin, TX']);
  });

  it('leaves the fixtures alone when the request throws', async () => {
    const practices: Practice[] = [toPractice(row({ slug: 'fixture' }))];
    const boom = vi.fn(async () => { throw new TypeError('network down'); }) as unknown as typeof fetch;
    await expect(loadListings(boom, practices, {})).resolves.toBe(false);
    expect(practices.map((p) => p.id)).toEqual(['fixture']);
  });

  it('leaves the fixtures alone when the body is not JSON', async () => {
    const practices: Practice[] = [toPractice(row({ slug: 'fixture' }))];
    const junk = vi.fn(async () => new Response('<html>', { status: 200 })) as unknown as typeof fetch;
    await expect(loadListings(junk, practices, {})).resolves.toBe(false);
    expect(practices.map((p) => p.id)).toEqual(['fixture']);
  });

  it('asks for the whole catalogue in one page, sends the session cookie and sets a deadline', async () => {
    const spy = ok([]);
    await loadListings(spy, [], {});
    expect(spy).toHaveBeenCalledWith('/api/listings?limit=200', {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal: expect.any(AbortSignal)
    });
  });

  it('asks for a LOAD_TIMEOUT_MS deadline and gives up when it fires', async () => {
    // Pre-flight I5: main.ts awaits this before bootstrap(), so a request that never settles is
    // a blank page, not the sign-in gate.
    //
    // The abort is driven through a spied `AbortSignal.timeout` rather than by advancing fake
    // timers: `AbortSignal.timeout` is implemented natively in Node and is not guaranteed to
    // observe vitest's fake clock, so a timer-driven version of this test could hang forever on
    // some Node builds. The spy pins BOTH halves of the contract — the deadline that was asked
    // for, and what happens when it fires — with no clock involved at all.
    const controller = new AbortController();
    const timeoutSpy = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(controller.signal);
    try {
      const practices: Practice[] = [toPractice(row({ slug: 'fixture' }))];
      const hangs = vi.fn(
        (_url: string, init?: RequestInit) =>
          new Promise<Response>((_resolve, reject) => {
            init?.signal?.addEventListener('abort', () =>
              reject(new DOMException('The operation was aborted.', 'TimeoutError'))
            );
          })
      ) as unknown as typeof fetch;

      const pending = loadListings(hangs, practices, {});
      expect(timeoutSpy).toHaveBeenCalledWith(LOAD_TIMEOUT_MS);
      controller.abort(new DOMException('The operation was aborted.', 'TimeoutError'));

      await expect(pending).resolves.toBe(false);
      expect(practices.map((p) => p.id)).toEqual(['fixture']);
    } finally {
      timeoutSpy.mockRestore();
    }
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/listings/load.test.ts`
Expected: FAIL — `Failed to resolve import "./load"`.

- [ ] **Step 3: Write the loader**

Create `frontend/src/listings/load.ts`:

```ts
// The app's one bridge from the API to the approved prototype's fixture arrays (spec
// 2026-09-06 D6). `logic.js` is the design file's script block, ported verbatim and never
// restructured, so this module does not reshape it: it MUTATES the exported `P` and `MARKETS`
// objects in place, and every reader inside `logic.js` — renderVals(), photoSet(),
// marketPanel() — sees the new data through the binding it already had.
//
// The field names below are the contract: they are the design's own, and the CLAUDE.md
// launch-removal note requires them to survive the removal of the fixtures themselves.

export const MARKET_ZOOM = 10;
// A hung request must not leave the app unmounted. `loadListings` is awaited before
// `bootstrap()`, so without a deadline a slow or black-holed /api/listings gives the member a
// BLANK PAGE — not the sign-in gate (pre-flight I5). Five seconds is far above the endpoint's
// 100 ms p95 budget and far below a user's patience.
export const LOAD_TIMEOUT_MS = 5000;
// The geographic centre of the contiguous United States: the only sane place to point a map
// for a market whose every listing has withheld its location.
export const US_CENTER: [number, number] = [39.8283, -98.5795];
const LIST_URL = '/api/listings?limit=200';

export interface ApiListing {
  id: string;
  slug: string;
  name: string | null;
  market: string;
  area: string;
  type: string;
  city: string;
  state: string;
  street: string | null;
  zip: string | null;
  phone: string | null;
  hours: string | null;
  price: number | null;
  rev: number | null;
  docs: number | null;
  rooms: number | null;
  sqft: number | null;
  bldg: string | null;
  est: number | null;
  listed: string;
  listed_at: string;
  status: string;
  pop: string | null;
  growth: string | null;
  income: string | null;
  hh: string | null;
  note: string | null;
  staff: string | null;
  services: string | null;
  facility: string | null;
  ownership: string | null;
  lat: number | null;
  lng: number | null;
  location_disclosed: boolean;
  photos: string[];
}

export interface Practice {
  id: string;
  area: string;
  type: string;
  price: number | null;
  rev: number | null;
  docs: number | null;
  rooms: number | null;
  sqft: number | null;
  bldg: string | null;
  lat: number | null;
  lng: number | null;
  est: number | null;
  listed: string;
  status: string;
  pop: string | null;
  growth: string | null;
  income: string | null;
  hh: string | null;
  note: string | null;
  staff: string | null;
  hours: string | null;
  services: string | null;
  facility: string | null;
  ownership: string | null;
  market: string;
  name?: string;
  photos?: string[];
}

export type Markets = Record<string, { center: [number, number]; zoom: number }>;

export interface ListingsPage {
  items: ApiListing[];
  next_cursor: string | null;
}

/**
 * One API row as the design's template reads it. `id` is the slug, not the uuid: the design
 * uses `p.id` as a DOM key and a fixture-map key, and a readable slug keeps that legible.
 * `name` and `photos` are added only when the API actually sent them, so an API row built
 * from a design fixture maps back to exactly that fixture — which is what keeps the pixel
 * gates honest (D6).
 */
export function toPractice(row: ApiListing): Practice {
  const p: Practice = {
    id: row.slug,
    area: row.area,
    type: row.type,
    price: row.price,
    rev: row.rev,
    docs: row.docs,
    rooms: row.rooms,
    sqft: row.sqft,
    bldg: row.bldg,
    lat: row.lat,
    lng: row.lng,
    est: row.est,
    listed: row.listed,
    status: row.status,
    pop: row.pop,
    growth: row.growth,
    income: row.income,
    hh: row.hh,
    note: row.note,
    staff: row.staff,
    hours: row.hours,
    services: row.services,
    facility: row.facility,
    ownership: row.ownership,
    market: row.market
  };
  if (row.name !== null) p.name = row.name;
  if (row.photos.length > 0) p.photos = row.photos;
  return p;
}

/** The mean position of `market`'s located practices, or the centre of the US if it has none. */
export function centroid(practices: Practice[], market: string): [number, number] {
  const located = practices.filter((p) => p.market === market && p.lat !== null && p.lng !== null);
  if (located.length === 0) return US_CENTER;
  const lat = located.reduce((sum, p) => sum + (p.lat as number), 0) / located.length;
  const lng = located.reduce((sum, p) => sum + (p.lng as number), 0) / located.length;
  return [lat, lng];
}

/**
 * Replace the fixture practices and reconcile the market table, both IN PLACE.
 *
 * A market the design already knows keeps its own centre and zoom: the design's Austin centre
 * is [30.31, -97.75] while the centroid of its nine Austin fixtures is about [30.36, -97.77],
 * and recomputing it would pan the map and fail a zero-tolerance visual gate for a reason
 * that has nothing to do with this change. A market with no listings left is dropped so the
 * metro selector never offers an empty one.
 */
export function applyListings(rows: ApiListing[], practices: Practice[], markets: Markets): void {
  const next = rows.map(toPractice);
  practices.length = 0;
  for (const p of next) practices.push(p);
  const wanted = new Set(next.map((p) => p.market));
  for (const key of Object.keys(markets)) {
    if (!wanted.has(key)) delete markets[key];
  }
  for (const key of wanted) {
    if (!(key in markets)) markets[key] = { center: centroid(next, key), zoom: MARKET_ZOOM };
  }
}

/**
 * Fetch the published listings and install them. Returns whether it did.
 *
 * A refusal (the anonymous 401 the identity design intends), an unreachable API, a request
 * that outlives `LOAD_TIMEOUT_MS` and an unparseable body all leave the design's fixtures in
 * place and return false — the screen must never go blank because a read failed, and the abort
 * surfaces as a rejected promise, which the `catch` below already handles. A 200 always wins,
 * empty list included: at that point the API is the source of truth and the design's own
 * "no results" state is the honest thing to show.
 */
export async function loadListings(
  fetchFn: typeof fetch,
  practices: Practice[],
  markets: Markets,
  url: string = LIST_URL
): Promise<boolean> {
  let page: ListingsPage;
  try {
    const response = await fetchFn(url, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(LOAD_TIMEOUT_MS)
    });
    if (!response.ok) return false;
    page = (await response.json()) as ListingsPage;
  } catch {
    return false;
  }
  applyListings(page.items, practices, markets);
  return true;
}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd frontend && npx vitest run src/listings/load.test.ts --coverage.include='src/listings/**'`
Expected: PASS, and `src/listings/load.ts` at 100 % lines, branches, functions and statements.

- [ ] **Step 5: Export the fixture arrays (RED → GREEN)**

In `frontend/tests/app-generated.test.ts`, change the port drift test's `FOOTER` constant:

```ts
  const FOOTER = '\nexport { Component, MARKETS, P };\n';
```

Run: `cd frontend && npx vitest run tests/app-generated.test.ts`
Expected: FAIL — `logic.js is the design script block, ported verbatim` fails; the file still ends `export { Component };`.

In `frontend/src/logic.js`, change the last line — and **only** the last line:

```js
export { Component, MARKETS, P };
```

Run: `cd frontend && npx vitest run tests/app-generated.test.ts && git diff --stat src/logic.js`
Expected: PASS; the diff is `1 file changed, 1 insertion(+), 1 deletion(-)`. **If it is anything larger, revert and start again** — the ported body is byte-identical by definition (Global Constraint (m)).

- [ ] **Step 6: Wire the load into the entry point (RED → GREEN)**

Rewrite `frontend/src/main.test.ts` so it stubs `fetch` and pins both outcomes:

```ts
// @vitest-environment jsdom
//
// The real entry point (index.html's <script type="module" src="/src/main.ts">): imports the
// app's singleton router (routes.ts, createWebHistory) and the two global stylesheets, loads
// the listings from the API, then bootstraps into '#app' by selector.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

beforeEach(() => {
  vi.resetModules();
  // A refused read is the ordinary signed-out case AND the case this test wants: the design's
  // fixtures survive, so the assertion below is about mounting, not about seeded data.
  vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 401 })));
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = '';
});

describe('main.ts', () => {
  it('bootstraps the real router into #app by selector after asking the API for listings', async () => {
    document.body.innerHTML = '<div id="app"></div>';

    await import('./main');
    await flush();
    await flush();

    expect(fetch).toHaveBeenCalledWith('/api/listings?limit=200', expect.anything());
    const root = document.getElementById('app');
    expect(root?.childElementCount).toBeGreaterThan(0);
  });
});
```

Run: `cd frontend && npx vitest run src/main.test.ts`
Expected: FAIL — `expected "spy" to be called with …` (nothing fetches yet).

Rewrite `frontend/src/main.ts`:

```ts
import { router } from './router/routes';
import './styles/tokens.css';
import './styles/global.css';
import { bootstrap } from './bootstrap';
import { loadListings } from './listings/load';
import type { Markets, Practice } from './listings/load';
// The ported prototype's fixture arrays. They are JavaScript with no declarations of their
// own, so each is cast once, here, at the single boundary where the two worlds meet; the
// shapes are pinned by frontend/src/listings/load.test.ts and by the visual gate.
import { MARKETS, P } from './logic.js';

// Listings first, then mount: a member sees the seeded eighteen on the first paint rather
// than the design's fixtures being swapped underneath them. A refusal or a failure leaves the
// fixtures in place and the sign-in gate is what the member sees anyway.
void loadListings(globalThis.fetch.bind(globalThis), P as unknown as Practice[], MARKETS as unknown as Markets)
  .then(() => bootstrap(router, '#app'));
```

Run: `cd frontend && npx vitest run src/main.test.ts && npx vue-tsc --noEmit -p tsconfig.json`
Expected: PASS, 0 type errors.

- [ ] **Step 7: Serve the design's own fixtures to the pixel gates (D6)**

Create `frontend/tests/design-listings.mjs`:

```js
// The design-fixture stub for the app Playwright project (spec 2026-09-06 D6).
//
// It is DERIVED from `logic.js`'s own arrays rather than hand-copied, so it can never drift
// from the design: `toApiShape` is the exact inverse of `load.ts`'s `toPractice`, which means
// the app under test reconstructs the design's practices field for field and every pixel
// still matches the design file. `name` is null and `photos` empty for the same reason — the
// design's fixtures carry neither, and `toPractice` adds those two keys only when the API
// sends them.
import { MARKETS, P } from '../src/logic.js';

export function toApiShape(p, i) {
  return {
    id: `00000000-0000-0000-0000-${String(i + 1).padStart(12, '0')}`,
    slug: p.id,
    name: null,
    market: p.market,
    area: p.area,
    type: p.type,
    city: p.area,
    state: (p.market || ', TX').split(', ')[1],
    street: null,
    zip: null,
    phone: null,
    hours: p.hours ?? null,
    price: p.price ?? null,
    rev: p.rev ?? null,
    docs: p.docs ?? null,
    rooms: p.rooms ?? null,
    sqft: p.sqft ?? null,
    bldg: p.bldg ?? null,
    est: p.est ?? null,
    listed: p.listed,
    listed_at: '2026-09-01T00:00:00+00:00',
    status: p.status,
    pop: p.pop ?? null,
    growth: p.growth ?? null,
    income: p.income ?? null,
    hh: p.hh ?? null,
    note: p.note ?? null,
    staff: p.staff ?? null,
    services: p.services ?? null,
    facility: p.facility ?? null,
    ownership: p.ownership ?? null,
    lat: p.lat ?? null,
    lng: p.lng ?? null,
    location_disclosed: true,
    photos: []
  };
}

export function designListingsBody() {
  return JSON.stringify({ items: P.map(toApiShape), next_cursor: null });
}
```

> No `export { MARKETS, P };` line here (pre-flight M6): nothing imports them from this module. `harness.ts` imports `designListingsBody`, and `load.test.ts` imports `P` and `MARKETS` from `../logic.js` directly. A re-export nothing consumes is one more thing to keep in step for no benefit.

In `frontend/tests/harness.ts`, add one route inside `prepare()`, after the existing `page.route` calls:

```ts
  // D6: the gates run against a stub that returns the DESIGN's own fixture practices in API
  // shape, so `load.ts` reconstructs exactly what `logic.js` already held and every pixel
  // still matches the design file. QA runs against the seeded eighteen instead.
  await page.route(/\/api\/listings(\?|$)/, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: designListingsBody() })
  );
```

and extend the file's imports with:

```ts
import { designListingsBody } from './design-listings.mjs';
```

- [ ] **Step 8: Prove the round trip before trusting the pixels**

Append to `frontend/src/listings/load.test.ts`:

```ts
describe('the design-fixture stub round-trips exactly (spec D6)', () => {
  it('every design practice survives toApiShape → toPractice unchanged', async () => {
    const { P } = await import('../logic.js');
    const { toApiShape } = await import('../../tests/design-listings.mjs');
    for (const [i, p] of (P as unknown as Practice[]).entries()) {
      expect(toPractice(toApiShape(p, i) as ApiListing)).toEqual(p);
    }
  });

  it('the design’s market centres survive applyListings unchanged', async () => {
    const { MARKETS, P } = await import('../logic.js');
    const { toApiShape } = await import('../../tests/design-listings.mjs');
    const before = JSON.parse(JSON.stringify(MARKETS));
    const practices = P as unknown as Practice[];
    applyListings((practices.map(toApiShape) as unknown) as ApiListing[], practices, MARKETS as unknown as Markets);
    expect(MARKETS).toEqual(before);
  });
});
```

Run: `cd frontend && npx vitest run src/listings/load.test.ts`
Expected: PASS. **This is the pixel guarantee in unit form** — if it fails, the visual gate is about to fail too, and the fix is in `toApiShape`/`toPractice`, never in the tolerance.

- [ ] **Step 9: Run every frontend gate**

> **`npm test` before `npm run build` measures the previous build** (pre-flight M8). `frontend/tests/bundle-budget.test.ts` reads `dist/_app`, so the first `npm test` below reports the bundle sizes of whatever was built last. That ordering is Browse V3's Global Constraint (g) and is kept deliberately — the authoritative run is `npx vitest run --coverage`, which comes **after** `npm run build` and is the one whose bundle numbers count. Do not reorder; do read the second run's numbers, not the first's.

```bash
cd frontend
npm run typecheck && npm test && npm run build
npx vitest run --coverage
npx vitest run tests/baseline-manifest.test.ts
npm run test:smoke
npm run test:visual
npx playwright test --config=tests/playwright.config.ts --project=app dom.spec.ts
```
Expected: 0 type errors; 100 % lines/branches/functions/statements on `src/**` (the exclude list unchanged); the **thirteen** frozen unchanged-screen hashes byte-identical; the smoke suite green; **27 visual states at `maxDiffPixels: 0`**; 27 DOM-oracle states green.

> **Thirteen, not fifteen and not fourteen (pre-flight I4).** Browse V3 freezes exactly thirteen baseline hashes in `frontend/tests/baseline-manifest.json`: `mobile-list`, `mobile-detail`, `detail`, `requests`, `seller-dash`, the four `wizard-*` and the four `admin-*`. `header-1100` and `header-1000` are deliberately **excluded** — they are Browse screenshots and are expected to move. Spec D9 says "the fourteen unchanged screens" and an earlier draft of this plan said fifteen; **both numbers are stale — the manifest is the authority**. → John: the spec sentence wants correcting when it is next touched.

If a Browse or detail state moves by even one pixel, the stub is not reconstructing the design's fixtures. Diff `toApiShape` against `toPractice` field by field, and **do not touch `playwright.config.ts`** (Global Constraint (n)).

- [ ] **Step 10: Commit**

```bash
cd "/Users/johndean/Development/Practice Match"
git add frontend/src/listings/load.ts frontend/src/listings/load.test.ts \
        frontend/src/logic.js frontend/tests/app-generated.test.ts \
        frontend/src/main.ts frontend/src/main.test.ts \
        frontend/tests/design-listings.mjs frontend/tests/harness.ts
git commit -m "feat(frontend): listings come from the API, keeping the design's field names

Spec 2026-09-06 D6. src/listings/load.ts fetches /api/listings at start-up and replaces
logic.js's P and MARKETS IN PLACE, so every reader inside the ported prototype sees the
new data through the binding it already had; the only edit to logic.js is its trailing
export line. A market the design already knows keeps its own centre and zoom — the
design's Austin centre differs from its fixtures' centroid, and recomputing it would pan
the map and fail a zero-tolerance gate. The Playwright harness serves a stub DERIVED from
those same fixtures, so the app reconstructs them field for field and all 27 visual states
still pass at maxDiffPixels: 0.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task L7: Seed QA, verify, and hand back

**Files:**
- Modify: `pyproject.toml` and `frontend/package.json` (one patch, in lockstep)
- No production change of any kind.

**Interfaces:**
- Consumes: everything L1–L6 produced.
- Produces: a seeded QA environment, screenshots, and the forwardable summary. Nothing later in the programme depends on an artefact of this task other than the merged branch.

- [ ] **Step 1: Bump the version in lockstep**

`tests/test_versions.py` fails unless `frontend/package.json`'s `version` equals `pyproject.toml`'s `[project].version`. Read the current value and raise the patch by exactly one, in both files:

```bash
cd "/Users/johndean/Development/Practice Match"
python3 -c "import tomllib,pathlib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text())['project']['version'])"
# edit pyproject.toml [project].version and frontend/package.json "version" to that value with
# the patch component incremented by one
poetry run pytest tests/test_versions.py -q
```
Expected: PASS.

- [ ] **Step 2: Run the whole gate, backend and frontend, one last time**

```bash
cd "/Users/johndean/Development/Practice Match"
docker compose -f docker-compose.dev.yml up -d
poetry run ruff check app tests scripts
poetry run mypy app --strict
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
bash tests/scripts/test_start_sh.sh
bash tests/scripts/test_deploy_guard.sh
bash tests/scripts/test_verify_deploy.sh
bash tests/scripts/test_verify_image_sh.sh
cd frontend
npm run typecheck && npm test && npm run build
npx vitest run --coverage
npm run test:smoke
npm run test:visual
npx playwright test --config=tests/playwright.config.ts --project=app dom.spec.ts
```
Expected: every command green. **Do not proceed on a single failure** (`superpowers:verification-before-completion`: evidence before assertions).

- [ ] **Step 3: Commit the version bump and push both remotes**

```bash
cd "/Users/johndean/Development/Practice Match"
git add pyproject.toml frontend/package.json
git commit -m "chore(release): bump version for the seed listings sub-project

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push origin HEAD
git push production HEAD
```

- [ ] **Step 4: Deploy to QA — after the 🚦 check**

```bash
cd "/Users/johndean/Development/Practice Match"
railway status              # MUST print Project: Practice Match — read it back before anything else
scripts/deploy.sh QA        # api + worker, then verify-deploy.sh QA
```
Expected from the verifier: `healthz OK  version X.Y.Z  commit <sha>  postgis 3.5.x`, `deep healthz OK`, `SPA fallback OK`. If `commit` is not this branch's HEAD short sha, the container is stale — redeploy before going further.

**Production is not deployed by this task.** Do not run `scripts/deploy.sh production`.

- [ ] **Step 5: Seed QA in the container**

```bash
railway status                                   # again — MUST print Project: Practice Match
railway ssh --service api --environment QA
# inside the container:
python scripts/seed_listings.py --reset
exit
```
Expected: `  - removed 0 existing seed listings` (the first run) then `[seed] done - 18 listings`. On a re-run the removed count is 18 and the result is the same eighteen rows — that is the idempotency D7 promises, observed live.

Exit 3 means the container could not reach Postgres — check `railway logs --service api --environment QA --lines 50`. Exit 4 means `seeds/` did not reach the image — confirm the `COPY seeds/ ./seeds/` line landed and redeploy. **Anything else, and in particular a Python traceback, means the image is wrong, not the data**: a `ModuleNotFoundError` here would mean `scripts/seed_listings.py` acquired a `from scripts.… import …` after all (pre-flight C1 — `sys.path[0]` inside the container is `/app/scripts`, not `/app`), which `tests/scripts/test_seed_listings.py::test_the_module_runs_as_a_bare_script_from_the_repo_root` exists to prevent. Do not chase `seeds/` for that symptom.

- [ ] **Step 6: Verify the deployment and read the data back over HTTP**

```bash
scripts/verify-deploy.sh QA
```
Expected: as in Step 4.

The listings endpoints are member-only, so verify them signed in through the browser rather than with an anonymous `curl`. The one thing `curl` should confirm is the refusal:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://qa.foundation.vin/api/listings
# expected: 401
curl -sS https://qa.foundation.vin/api/listings | python3 -m json.tool
# expected: {"error": {"code": "UNAUTHORIZED", "message": "Sign in to continue."}}
```

- [ ] **Step 7: Click through https://qa.foundation.vin**

Sign in as an approved member, then confirm every line below. **Any line that fails is a STOP.**

1. **Browse Practices** shows result cards for the seeded hospitals, and **all twenty-one design fixtures are gone** — not just the nine Austin ones (pre-flight I3: the design ships p1–p9 in Austin *plus* c1–c4 Sacramento, o1–o4 Orlando and g1–g4 Atlanta). Check one fixture in each of the four design markets and confirm each is absent: **Cedar Park** (Austin), **Roseville** (Sacramento), **Winter Park** (Orlando), **Marietta** (Atlanta). Finding only the Austin nine gone means the market filter, not the seed, changed what you are looking at.
2. The metro selector lists the eleven seeded markets — Dallas TX, New York NY, Denver CO, Santa Barbara CA, Houston TX, Los Angeles CA, South Lake Tahoe CA, Sacramento CA, Orlando FL, Atlanta GA, Austin TX — and no market with zero listings.
3. Each of the **eighteen** appears as a pin at its real address. Walk every market and count: Dallas 1, New York 1, Denver 1, Santa Barbara 1, Houston 2, Los Angeles 3, South Lake Tahoe 1, Sacramento 3, Orlando 2, Atlanta 1, Austin 2 = 18.
4. Spot-check three pins against the street address by eye on the map: `17727 Dallas Pkwy` (far North Dallas, off the Tollway), `510 E 62nd St` (Manhattan, Upper East Side), `921 Emerald Bay Rd` (South Lake Tahoe, on the lake's south shore). A pin in the wrong city is a bad geocode — STOP.
5. **"Tiles © Esri" attribution is visible on every map** (desktop Browse, the mobile Map tab). Legally load-bearing — CLAUDE.md.
6. Open a listing's **detail** screen: the card fields (price, revenue, doctors, rooms, sq ft, building, established, staff, hours, services, facility, ownership) carry the seeded demo values, and the note reads "Demo listing seeded by the VIN Foundation."
7. **Community Context** shows its empty state — D4 leaves `pop`/`growth`/`income`/`hh` null until the Census plan.
8. **Photographs**: if Step 0 found that V3 reads `p.photos`, the detail screen shows the seeded photographs and each loads (check the network tab for `200 image/webp` on `/api/listings/<id>/photos/1`). If Step 0 found it does not, record that the slots are empty and that John's ruling is outstanding — **do not patch it here**.
9. **Names**: same conditional as (8) for the title slot (D5).
10. **Mobile** (Chrome device toolbar, 390 × 800): the list and the Map tab both show the seeded hospitals; the market-data sheet opens and closes.
11. Sign out and reload `/browse`: the **sign-in gate** appears, not a blank screen — the anonymous 401 leaves the design fixtures and the gate does its job (D8).

- [ ] **Step 8: Screenshots**

Capture and attach to the hand-back: (1) Browse Practices at 1440 × 940 showing the seeded results rail and the pins; (2) the metro selector open, listing the eleven markets; (3) one detail screen with its demo figures and the empty Community Context; (4) the map zoomed to Dallas with the pin on the Tollway; (5) the mobile Map tab at 390 × 800 with the attribution visible; (6) the signed-out `/browse` gate.

- [ ] **Step 9: Write the forwardable summary**

Plain language, no jargon, forwardable to the VIN Foundation as is. Fill in the real numbers:

> **Practice Match — demo hospitals now live on the test site**
>
> The test site at qa.foundation.vin now shows eighteen demo veterinary hospitals instead of
> the twenty-one placeholder practices the design shipped with (nine around Austin plus four
> each in Sacramento, Orlando and Atlanta). Each one uses the hospital names you supplied,
> sits at its real street address on the map, and carries a fake 555 phone number, its opening
> hours and up to four of the photographs you sent. Everything else about the screens is
> unchanged.
>
> Two small things to know. The screens show each hospital's opening hours and put its pin at
> the real address, but there is no place in the approved design to print the street address or
> the phone number, so those are stored and available without being displayed. And the hospital
> names and photographs are stored and served, but the approved design still takes its titles
> and photographs from its own built-in sample list — see the note below.
>
> The addresses were placed on the map using the U.S. Census Bureau's own free address
> service — no Google data is stored anywhere. The business figures (asking price, revenue,
> number of doctors, and so on) are plausible demo values we can change at any time; say the
> word and we will. The community statistics panel is deliberately empty until the Census data
> work lands.
>
> The live site at foundation.vin is untouched and still shows the Coming Soon page.
>
> **Engineer's note (one line, with any risk):** the eighteen hospitals are seeded by an
> idempotent script inside the QA container (`scripts/seed_listings.py --reset`); the one risk
> is that a re-run without `--reset` would leave a stale hospital behind if a slug is ever
> renamed — rename a slug only together with a `--reset` run.

Step 0's probe will have found that the V3 design does **not** read `p.name` or `p.photos`. Add this to the note (it is written to be forwardable as it stands):

> **Outstanding decision — hospital names and photographs on screen.** The approved design still
> takes each practice's title and photographs from its own built-in sample list rather than from
> the listing, so the names and photographs you supplied are stored and served correctly but do
> not yet appear in the title and photo slots. There are five places in the design script that do
> this (the title, two photo-gallery branches, and the two thumbnail helpers).
>
> Our recommendation: **change the design file itself** so it prefers the listing's own name and
> photographs, and re-issue it as V3.1. That is the cleanest route — the code stays a faithful
> copy of the design, the pixel-comparison gate keeps working untouched, and nothing has to be
> re-done by hand at the next handoff. The fallback, if the design canvas cannot be re-opened
> this wave, is to add five named, tested rewrite rules to our port step; it works, but it is
> five brittle text substitutions and needs a written amendment to the platform spec. A hand edit
> to the ported file is **not** an option — it would break the byte-for-byte gate the Browse V3
> work just put in place, and would be lost at the next handoff.
>
> **A second, related decision — photo captions.** The design gives each hospital six fixed,
> captioned photo slots ("Reception and waiting", "Exam room", and so on). The seeds supply at
> most four photographs, in the order your folders list them, and for several hospitals the first
> four are all exteriors — so dropping them into the slots in order would caption an exterior
> photograph "Reception and waiting". We have recorded what each photograph actually shows
> (derived from your filenames) alongside the files, so whichever route is chosen above can use
> it. Tell us whether you would rather match photographs to slots by subject, or show the four we
> have under neutral captions.
>
> **A third, smaller one — the address and phone number.** There is no place in the approved
> design to print a practice's street address or telephone number; the design shows the area, the
> type and the map pin. Both are stored and served, so a future screen can show them, but nothing
> displays them today. Confirm that is fine for now.

- [ ] **Step 10: Confirm production is untouched and finish the branch**

```bash
cd "/Users/johndean/Development/Practice Match"
curl -sS https://foundation.vin/api/healthz | python3 -m json.tool | grep -E 'site_mode|environment'
# expected: "environment": "production", "site_mode": "coming_soon"
git log --oneline origin/main..HEAD
git push origin HEAD && git push production HEAD
```
Expected: production still reports `coming_soon`; the branch's commits are on both remotes.

Then use `superpowers:finishing-a-development-branch` to decide how the branch is integrated.

---

## Self-Review

Run against the spec with fresh eyes, per the writing-plans skill.

**1. Spec coverage.**

| Spec item | Task | Test that proves it |
|---|---|---|
| §1 eighteen hospitals replace the design's fixtures (**twenty-one**, not nine — §1's number is stale), QA only, production unaffected | L4, L7 | `test_seed_writes_eighteen_published_seed_rows`; L7 Step 7 item 1 (one fixture checked per design market) and Step 10 |
| §2 John's table, verbatim | L2 | `test_johns_table_is_reproduced_verbatim_and_in_order`, and — because that is a hand-typed second copy — `test_the_seed_file_reconstructs_the_spec_table_exactly` parsed straight out of the spec's own markdown |
| §2 photograph source folders | L3 | `test_source_images_are_sorted_and_exclude_non_images`, `test_every_seeded_hospital_has_photographs` |
| D1 the `listing` table and every named column | L1 | `test_listing_has_exactly_the_contracted_columns` |
| D1 migrations start at `015` | L1 | the filename; `ls migrations/01[0-4]_*.sql` in Preconditions |
| D2 Census Geocoder, coordinates + tier committed | L2 | `test_the_geocode_provenance_is_recorded`, `test_no_geocode_placeholder_survived_the_run`, `test_the_dallas_anchor_is_the_probed_coordinate` (with a documented recourse for a rolling-benchmark change) |
| D2 state bbox + ≤ 25 km from centroid, no network in tests | L2 | `test_every_point_is_inside_its_states_bounding_box`, `test_every_point_is_within_25_km_of_its_city_centroid` |
| D2 no Google content stored | L2, Constraint (h) | the geocode block calls only `geocoding.geo.census.gov`; nothing in `seeds/` names Google |
| D3 ≤ 4 per hospital, folder order | L3 | `test_prepare_keeps_at_most_four_in_folder_order` |
| D3 WebP ≤ 1600 px, ≤ 250 KB, metadata stripped | L3 | `test_every_output_is_webp_within_the_dimension_and_size_ceilings`, `test_metadata_is_stripped` + `test_the_fixture_sources_really_carry_metadata` (the fixtures carry real EXIF/GPS and a real ICC profile, so the stripping can actually fail), `test_encode_gives_up_rather_than_writing_an_oversized_file` |
| D3 inventory with SHA-256s; committed outputs | L3 | `test_the_inventory_records_a_matching_sha256_and_dimensions`, `test_every_committed_file_matches_its_recorded_hash_and_size`, `test_every_committed_photograph_has_a_caption_and_a_source` |
| D3 size ceiling (≈ 15 MB, hard 18 MB) | L3 | `test_the_committed_set_stays_under_the_size_ceiling` |
| D3 served by the API, not bundled | L5, L4 | `test_photos_are_served_as_webp_with_a_private_cache_header`, `test_photos_are_refused_to_an_anonymous_caller`, `test_a_photograph_of_a_seeded_hospital_is_really_served`; and `seeds/` is proved to be **inside the built image** by `scripts/verify-image.sh` + its negative case, not merely present in the Dockerfile's text |
| D4 `type` derivation | L2 | `test_type_is_derived_exactly_as_d4_says`, `test_the_derivation_produces_five_specialty_four_emergency_and_nine_small_animal` |
| D4 demo business fields, `"demo": true`, the note | L2 | `test_the_demo_business_fields_are_present_and_plausible`, `test_every_row_is_a_published_disclosed_demo_seed` |
| D4 community figures null | L2, L5 | `test_community_figures_are_absent_until_the_census_plan_supplies_them`; `serialise` returns them as `null` |
| D5 name stored and shown in a title slot | L2, L5, L6 | stored and served (`test_every_row_carries_the_seed_files_own_values`, the JSON contract); **shown** is the STOP in L6 Step 0 |
| D6 stubbed `/api/listings` for the gates | L6 | `the design-fixture stub round-trips exactly`; `npm run test:visual` at zero tolerance |
| D6 replace `P`/markets keeping field names | L6 | `toPractice` maps every design name; `applyListings` mutates in place |
| D7 idempotent upsert by `slug`, `--reset` | L4 | `test_seed_is_idempotent`, `test_reset_removes_seed_rows_but_never_seller_rows` |
| D7 runs in-container / `seed` role | L4, L7 | `tests/scripts/test_start_sh.sh`; L7 Step 5 |
| D7 never on production without John's go | Constraint (j), L4 DEPLOY.md, L7 Step 10 | `test_deploy_md_documents_how_to_seed_qa` |
| D8 `listing.read` on all three routes, anonymous 401 | L5 | `test_anonymous_gets_the_generic_401_body`, `test_the_listings_routes_are_guarded_not_public` |
| D8 published only, `?market=`, paginated | L5 | `test_unpublished_listings_are_hidden_from_both_endpoints`, `test_the_market_filter_narrows_the_list`, `test_pagination_walks_every_row_exactly_once` |
| D8 pins use the geocoded point; `location_disclosed` | L5 | `test_an_undisclosed_listing_returns_no_address_and_no_point`, `test_serialise_blanks_the_address_of_an_undisclosed_listing`, `test_serialise_omits_a_point_a_disclosed_listing_never_had` |
| D9 perf budgets in `tests/perf/test_api_latency.py` | L5 | `test_listings_p95_within_budget` |
| D9 100 % backend and frontend | every task's gate step | `--cov=app --cov=scripts --cov-branch --cov-fail-under=100` (baseline established in the Preconditions, enforced on every PR by L5 Step 6b's `quality.yml` edit); `npx vitest run --coverage`. Every arm no request can reach has a **named** test in the task that writes it — `test_encode_gives_up_rather_than_writing_an_oversized_file`, `test_main_returns_two_when_an_image_will_not_fit`, `test_main_returns_four_when_the_seed_file_has_no_hospitals`, `test_main_returns_four_when_the_hospitals_key_is_not_a_list`, `test_main_returns_four_when_the_photo_inventory_is_absent`, `test_row_params_names_the_missing_field`, `test_an_over_long_market_is_a_400_in_the_a5_shape`, `test_photo_list_accepts_both_a_list_and_a_json_string`, `test_serialise_handles_photos_arriving_as_a_json_string`, `test_serialise_omits_a_point_a_disclosed_listing_never_had` |
| D9 zero regression on the unchanged screens (**thirteen** frozen hashes — D9's "fourteen" is stale) | L6 | `tests/baseline-manifest.test.ts` + `npm run test:visual` at `maxDiffPixels: 0` |
| D7 the seeder actually runs in the container | L4 | `test_the_module_runs_as_a_bare_script_from_the_repo_root`, `test_the_module_runs_as_a_bare_script_from_any_working_directory`, `test_normalize_dsn_agrees_with_the_migration_runner` |
| §4 out of scope (wizard, publishing, admin tab, market data, production seeding) | — | no task touches them |

**Gap found and closed inside the plan:** D1 names the column `listed_at`, while the design's field is the relative string `listed`. Task L5 stores `listed_at` and renders `listed` on the server (`relative_listed`), so the frontend never computes it and the pixel gates cannot drift with the wall clock. Task L2 carries `listed_days_ago` rather than an absolute date for the same reason.

**Gap found and escalated, not closed:** D5 and D3 both assume the design reads `p.name` and `p.photos`. **It does not** — verified against the V3 design file itself, where `grep` for each returns zero hits, across **five** sites (`practiceName`, `photoSet`'s two branches, `heroSrc`, and V3-only `thumbSrc`). Task L6's STOP note enumerates all five and lays out three options, recommending that the **design file** be changed and re-issued as V3.1, with named rewrite rules in the port step as the fallback; a hand edit to the ported `logic.js` is rejected outright because it would break the byte-exact drift test Browse V3 builds. The data is stored and served either way. Two smaller decisions travel with it: photo captions (the design has six fixed captioned slots, the seeds supply four files in filename order — L3 records a derived caption per file so any mapping can use it) and the fact that `street` and `phone` reach no screen because the design has no field for them (L6's Interfaces note). All three are written up, forwardable, in L7 Step 9.

**Gap found and closed inside the plan (executability):** `scripts/seed_listings.py` cannot import from `scripts/` — the container runs it as `python scripts/seed_listings.py`, which puts `/app/scripts` on `sys.path[0]` and the repo root nowhere, and `scripts/` has no `__init__.py`. `normalize_dsn` is therefore defined locally, pinned to `scripts/migrate.py`'s by a parity test, and two subprocess tests run the file exactly as the container will — the only shape of test that can catch this, since pytest and `runpy` both start with the repo root already on the path.

**2. Placeholder scan.** No "TBD", no "TODO", no "implement later", no "similar to Task N", no "add appropriate error handling", and **no deferred coverage** — the sentence that used to say "add a unit test if the arm is uncovered" is gone, replaced by the named tests listed in the D9 row above. Every code step carries real code.

Three assertions were checked for honesty rather than presence: the slug/folder assertion is now a set membership (a string concatenation is always truthy); `test_metadata_is_stripped` now runs against fixtures that genuinely carry EXIF, GPS and an ICC profile, so deleting the stripping fails it; and `test_the_geocode_provenance_is_recorded` is joined by `test_no_geocode_placeholder_survived_the_run`, because `"tier": "exact"` is pre-filled and `"REPLACE FROM THE GEOCODER RUN"` is a non-empty string that the old check would have accepted.

The two places that read like gaps are deliberate and named: the `0.0` / `REPLACE FROM THE GEOCODER RUN` values in `seeds/hospitals.json` (they are the output of the one step that must be run live, and both the bounds test and the placeholder test fail until they are replaced — that is the mechanism, not an omission) and L6 Step 0's STOP (a decision that is John's, with all three options spelled out and one recommended).

**Cross-plan note (pre-flight M7).** The Census plan's `tests/census/listing_fixtures.make_listing` inserts only `(id, street, city, state, zip, status)`, which will violate the `NOT NULL` on `slug`, `name`, `area`, `type`, `market` and `source` once `015_listing.sql` exists. The Census plan already anticipates this — "adapt the column list to SP2's schema in this one helper only" — so it is a note, not a defect, and no task here changes that file. Whoever executes the Census plan after this one should expect to add those six columns to that single helper.

**3. Type consistency.** Checked end to end:
- `slug` is the join between L2's seed file, L3's folder names and inventory keys, L4's `photo_paths`, and L6's `Practice.id`. One spelling throughout.
- `photos` is `list[str]` of `"<slug>/<n>.webp"` in the database (L3/L4) and `string[]` of `"/api/listings/<id>/photos/<n>"` in the JSON (L5) and in `Practice.photos` (L6). The two shapes are different on purpose and the boundary is `serialise`.
- `listed_days_ago` (L2, int) → `listed_at` (L1/L4, timestamptz) → `listed` (L5, string) → `Practice.listed` (L6, string). One chain, three names, each defined where it is produced.
- `relative_listed`, `encode_cursor`, `decode_cursor`, `serialise`, `photo_list`, `photo_file`, `LIST_TTL_S` are the exact names L5's tests import. `serialise` is declared **and** implemented as `serialise(row: Mapping[str, Any], now: datetime) -> dict[str, Any]` — the Interfaces block and the code now agree (the earlier draft declared `Mapping` and implemented `dict`).
- The `jsonb` `photos` value is decoded in exactly one place, `photo_list(value: object) -> list[str]`, called by both `serialise` and `get_listing_photo`. The defensive ternary that used to be written twice is gone, so there is one pair of arms to cover rather than two.
- **The L1 → L5 → L6 column chain, re-walked field by field.** `EXPECTED_COLUMNS` (L1) minus the four housekeeping columns (`id`, `source`, `created_at`, `updated_at`) is exactly what `_SELECT`/`_COLUMNS` (L5) reads, with `geom` split into `lat`/`lng` by `ST_Y`/`ST_X`. `serialise` emits those plus `listed` (derived), the four `null` community figures and `photos` (rewritten to URLs). `toPractice` (L6) consumes that JSON and emits the design's own 25 keys — `id, area, type, price, rev, docs, rooms, sqft, bldg, lat, lng, est, listed, status, pop, growth, income, hh, note, staff, hours, services, facility, ownership, market` — plus optional `name`/`photos`. The seven API fields with no design home (`slug` becomes `id`, `street`, `city`, `state`, `zip`, `phone`, `listed_at`, `location_disclosed`) are dropped deliberately and that is now stated in L6's Interfaces and in the hand-back note.
- `relative_listed(listed_at, now)` is the only producer of `listed`; it is server-side in L5, the design-fixture stub supplies `listed` verbatim, and `toPractice` copies it through. Nothing on the frontend ever computes it, so no wall-clock drift can reach a baseline.
- `toPractice`, `centroid`, `applyListings`, `loadListings`, `MARKET_ZOOM`, `US_CENTER`, `LOAD_TIMEOUT_MS` are the exact names L6's tests import, and `toApiShape(practice, index)` in `design-listings.mjs` is their inverse — same arity in the module, in `designListingsBody()`'s `P.map(toApiShape)` and in the round-trip test's `toApiShape(p, i)`.
- `REQUIRE_LISTING_READ` is one module constant, never wrapped (Constraint (g)); `PUBLIC_ROUTES` is untouched (Constraint (e)).
- `seed(dsn, *, reset=False) -> int` is the one signature L4's tests and L5's end-to-end test both call. `normalize_dsn(dsn: str) -> str` exists in both `scripts/migrate.py` and `scripts/seed_listings.py` by design, with a parity test binding them.
- `caption_of(source_name: str) -> str` (L3) writes `index.json`'s `caption`; L3's inventory test is its only consumer today, and it is the data whichever option John picks for the photo slots will read.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-09-06-practice-match-seed-listings.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between tasks, fast iteration. **REQUIRED SUB-SKILL:** `superpowers:subagent-driven-development`.

**2. Inline Execution** — execute tasks in this session with checkpoints. **REQUIRED SUB-SKILL:** `superpowers:executing-plans`.

**Which approach?**
