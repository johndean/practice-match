# Practice Match Map Engines and Layer Eligibility (Sub-project 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-05-map-engines-design.md` (approved 2026-09-05). **Prerequisites:** Platform plan through Task 1b (the `MapEngine` interface and `LeafletMapEngine` — see the Platform plan), Census plan Tasks A1 (registry) and A9 (gate, admin data-sources API). The Google Cloud project, keys, Map ID, quotas and budget are the Google plan's **Task G1** (John) and must exist before `map_engine_google` can be cleared.

**Goal:** Two map engines behind one interface, exactly one active per environment, chosen by an Admin **Activate** action, with every layer's eligibility per engine encoded as a licence fact in the registry — and nothing from Google ever stored.

**Architecture:** The server renders the SPA shell per request from a 15-second in-process snapshot (active engine, gate version, enabled rows, CSP), preloading only the active engine's chunk; the browser reads that config and imports one engine module. `dataset_registry` gains `kind`, `engines`, `active`; the single eligibility rule (`cleared ∧ active engine ∈ engines`) lives in `app/census/gate.py` and drives `/api/layers`, `/api/map-config` and the CSP. Activation is a transactional two-step swap on `/api/admin/data-sources/{key}/activate`, written to an append-only change log and bumping the existing gate counter.

**Tech Stack:** FastAPI + SQLAlchemy async + psycopg2 (as in the Census plan), Redis (gate counter, rate limits), Vue 3 + Vite (manual chunks per engine), Leaflet 1.9.4 (vendored, Platform Task 1), Maps JavaScript API (`v=weekly`, `maps`/`marker`/`places` libraries), Vitest + jsdom with deterministic Leaflet/Google stubs, Playwright.

## Global Constraints (exact values — from the spec)

- **Quality and performance policy (`docs/superpowers/specs/2026-09-05-quality-and-performance-policy.md`).** Test shape ~70/20/10 unit/integration/e2e enforced by rules; CI gates: `pytest -W error --cov-fail-under=90`, `diff-cover --fail-under=100`, `ruff`, `mypy --strict`, `vue-tsc --noEmit` (strict), vitest coverage ≥ 85 % on `src/map|router|admin`, Playwright fails on any `pageerror`/`console.error`, `gitleaks`; performance budgets are tests: API p95 (`/api/healthz` ≤ 20 ms, shell ≤ 15 ms, list endpoints ≤ 100 ms, panel ≤ 150 ms), bundle sizes (main ≤ 220 KB gz, `engine-leaflet` ≤ 60, `engine-google` ≤ 12, first load ≤ 300), first map paint ≤ 1,500 ms, hot queries use indexes, nightly k6 on QA (p95 ≤ 400 ms, 0 errors). Raising a budget is a reviewed change with a reason in the commit message.
- **TDD, no exceptions (John, 2026-09-05: "everything must have tests").** Every production change begins with a failing test that is run and watched fail (RED), then the minimal code, then the same test watched pass (GREEN) — the `Run:` lines in each task are mandatory steps, not illustrations. Documentation and configuration are covered by drift tests (`tests/test_docs.py`: every setting in `.env.example` and `DEPLOY.md`, relative links resolve, CI workflow shape, runbook endpoints exist); operational scripts have shell tests under `tests/scripts/` that run them against stubbed servers or a stubbed `curl`; ops steps end with an executable verification whose script is itself tested. The handoff's generated UI is covered by the visual gate (every screen state), the route smoke tests, the router-sync and engine unit tests and the `logic.js` characterisation suite (Platform Task 1c); new code in those files follows TDD.
- **One engine active per environment, never per user or per screen** (Google Maps Platform Terms §3.2.3(e)). The inactive engine's JavaScript chunk, CSS and tile hosts are never requested — proved by e2e route interception (Task M7).
- **Only `frontend/src/map/engines/*.ts` and `frontend/src/lib/leaflet.js` may import `leaflet` or the Google loader** — enforced by the import-boundary test (`frontend/src/map/boundary.test.ts`, Platform Task 1b).
- **Nothing from Google is stored.** No Places field and no Aggregate count is written to Postgres, Redis (other than rate-limit counters), the bucket, logs or analytics. Lat/lng of a place may live in browser memory for the page's life only.
- **Attribution untouched.** `disableDefaultUI: true` removes controls only; the Google logo, "Map data ©" and Terms link are never hidden, moved or restyled.
- **Default engine: Leaflet.** `map_engine_leaflet` is `cleared` and `active` at seed; `map_engine_google` is `unresolved` until Google plan Task G1's verification.
- **Eligibility rule (one implementation, `gate.enabled`):** `row.license_status = 'cleared' ∧ active_engine_name ∈ row.engines`, where `active_engine_name` = the active engine row's `dataset_key` minus the `map_engine_` prefix, or `'leaflet'` when no cleared active row exists.
- **Shell rendering:** no I/O per request — engine chunk filenames globbed from `frontend/dist/_app/engine-*.js` at process start; snapshot TTL **15 s**; `Cache-Control: no-cache`; weak `ETag` = hash(chunk names, engine, gate, authenticated flag); inlined JSON escapes `<`, `>`, `&`, U+2028, U+2029 as `\uXXXX`.
- **Google runtime config (`mapId`, `browserKey`) is inlined only in authenticated shells** — a valid member session (SP2) or, before SP2, `MARKET_DATA_PUBLIC=true` (QA only, never production). Values come from the `api` service environment (`GOOGLE_MAPS_BROWSER_KEY`, `GOOGLE_MAPS_MAP_ID`), never from the build.
- **CSP per page = union of the enabled rows' allowlists** (constants in `app/shell.py:CSP_HOSTS`); `style-src 'self' 'unsafe-inline'` (the design uses inline styles); `img-src 'self' data: blob:` plus the enabled tile/imagery hosts.
- **Activation:** one transaction — `UPDATE … SET active=false WHERE kind='engine'` then `UPDATE … SET active=true WHERE dataset_key=:k AND kind='engine' AND license_status='cleared'` (0 rows → 409); idempotent no-op on the already-active engine (no log row, no gate bump); `5` activations per minute per environment; `ADMIN_ACTIVATE_ENABLED` default **false on production** until SP2 ships; CSRF: bearer-token callers exempt, cookie sessions must send `X-CSRF-Token` equal to the `pm_csrf` cookie.
- **Change log:** `registry_change_log` append-only for the application role; rows carry actor, IP, user agent, field, old/new value, reason.
- **Reconciliation:** every `/api/*` response carries `X-PM-Gate: <version>`; clients refetch `/api/layers` and `/api/map-config` on the next route change when it changes — **no polling**; a map component enables only layers whose `engines` include the engine it **mounted**.
- **Runtime rules:** one long-lived map instance per session (re-parented between screens; `show()` after re-parenting); Places calls debounced 300 ms and memoised per (hub, band); **no client-side engine swap** — a failed engine shows the design's "Map unavailable" panel.
- **`/api/layers` response shape becomes `{ "engine": "leaflet", "gate": 42, "layers": [ … each entry with "engines": [...] ] }`** (Census plan API contract and B5 tests updated in Task M9).
- **Migration numbering:** this sub-project owns `080`–`089`. SP2/identity `010`–`015`, Seed Listings `016`, Census SP3-A `017`–`059`, SP3-B `060`+. The Google plan's `009_google_registry.sql` (Task G5) is **not** created — superseded by `080`.
- **Testing:** `app-leaflet` (the existing `app` project) keeps the full visual gate at `maxDiffPixels: 0`; `app-google` runs smoke, the map screens and the no-mixing assertions with the map viewport masked; no live Google key in CI or GitHub — the stub only.
- Every commit: conventional message, `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, pushed to `origin` and `production`. Work on `feat/map-engines` in a worktree. Before any `railway up` or variable change: `railway status` must print `Project: Practice Match`.

## File map

| File | Responsibility |
|---|---|
| `migrations/080_map_engines.sql` | `kind`, `engines`, `active` columns; one-active index; trigger rules; `registry_change_log`; engine/basemap/layer rows |
| `app/census/registry.py` | `Dataset` gains `kind`, `engines`, `active`; `COLUMNS` extended |
| `app/census/gate.py` | `engine_name`, `active_engine`, `enabled` — the one eligibility rule |
| `app/shell.py` | Snapshot (15 s TTL), `CSP_HOSTS`, `build_csp`, `escape_json`, `render_index`, `etag`, `engine_chunks` |
| `app/static.py` | Serves the rendered shell for `/` and SPA fallbacks; unchanged asset serving |
| `app/main.py` | `X-PM-Gate` header middleware for `/api/*`; router wiring |
| `app/config.py` | `google_maps_browser_key`, `google_maps_map_id`, `admin_activate_enabled` |
| `app/api/map_config.py` | `GET /api/map-config` |
| `app/api/market.py` | `/api/layers` uses `gate.enabled`; new shape |
| `app/api/admin_data_sources.py` | `/activate`, `/changes`; `/license` writes the change log; row fields |
| `app/api/csrf.py` | `require_csrf` (bearer exempt; cookie double-submit) |
| `frontend/vite.config.ts` | `manualChunks` → `engine-leaflet`, `engine-google` |
| `frontend/src/map/config.ts` | `readShellConfig`, `fetchMapConfig`, `ShellConfig` |
| `frontend/src/map/gate.ts` | `apiFetch` (records `X-PM-Gate`), `gateChanged`, `installGateWatcher(router)` |
| `frontend/src/map/create.ts` | `createEngine(cfg)` — imports exactly one engine module |
| `frontend/src/map/host.ts` | `useMapHost()` — the one long-lived engine instance, attach/detach |
| `frontend/src/map/engines/google.ts`, `google-loader.ts`, `google.css` | `GoogleMapEngine` implementing `MapEngine` |
| `frontend/src/map/eligibility.ts` | `enabledFor(layer, mountedEngine)` |
| `frontend/src/map/testing/google-stub.ts` | Deterministic `google.maps` for Vitest and Playwright |
| `frontend/src/admin/dataSources.ts` | API rows → the Data tab's cell shape; engine rows; two-click Activate state machine |
| `frontend/e2e/engines.spec.ts`, `frontend/tests/playwright.config.ts` | `app-google` project; no-mixing, preload, activation e2e |
| `DEPLOY.md`, `docs/RUNBOOK-map-engines.md` | Variables, activation runbook, quota response |

---

### Task M1: Migration `080`, registry model, the eligibility rule

**Files:**
- Create: `migrations/080_map_engines.sql`, `tests/census/test_map_engines_registry.py`
- Modify: `app/census/registry.py` (`COLUMNS`, `Dataset`), `app/census/gate.py` (append three functions), `tests/census/test_registry.py` (`SPEC_KEYS`)

**Interfaces:**
- Consumes: `dataset_registry` (Census A1), `registry.load(conn) -> dict[str, Dataset]`, `registry.Dataset.cleared`, `gate.layer_enabled/invalidate/version` (A9).
- Produces: `Dataset.kind: str`, `Dataset.engines: list[str]`, `Dataset.active: bool`; `gate.ENGINE_PREFIX = "map_engine_"`; `gate.engine_name(dataset_key: str) -> str`; `gate.active_engine(reg: dict[str, Dataset]) -> Dataset | None` (the cleared, active engine row, else `None`); `gate.active_engine_name(reg) -> str` (`'leaflet'` fallback); `gate.enabled(row: Dataset, reg: dict[str, Dataset]) -> bool`; table `registry_change_log`.

- [ ] **Step 1: Failing tests**

`tests/census/test_map_engines_registry.py` (uses the Census plan's `conn` fixture — a scratch database with all migrations applied):
```python
import psycopg2
import pytest

from app.census import gate
from app.census.registry import load


def test_engine_rows_and_columns_are_seeded_with_leaflet_active(conn):
    reg = load(conn)
    assert reg["map_engine_leaflet"].kind == "engine" and reg["map_engine_leaflet"].active is True and reg["map_engine_leaflet"].cleared
    assert reg["map_engine_google"].kind == "engine" and reg["map_engine_google"].active is False and reg["map_engine_google"].license_status == "unresolved"
    assert reg["esri_tiles"].kind == "basemap" and reg["esri_tiles"].engines == ["leaflet"] and reg["esri_tiles"].license_status == "unresolved"
    assert reg["osm_tiles"].kind == "basemap" and reg["osm_tiles"].engines == ["leaflet"]
    assert reg["imagery"].engines == ["leaflet"]
    assert reg["acs5"].kind == "dataset" and reg["acs5"].engines == ["leaflet", "google"]
    assert reg["google_places_live"].engines == ["google"] and reg["google_places_aggregate"].engines == ["google"]
    assert reg["places_ui_kit"].engines == ["leaflet", "google"] and reg["google_maps_link"].cleared
    assert reg["practice_locations"].engines == [] and reg["practice_locations"].license_status == "blocked"


def test_exactly_one_engine_can_be_active(conn):
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.UniqueViolation):
        cur.execute("UPDATE dataset_registry SET active = true WHERE dataset_key = 'map_engine_google'")  # google is not cleared → trigger fires first
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='cleared' WHERE dataset_key='map_engine_google'")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute("UPDATE dataset_registry SET active = true WHERE dataset_key = 'map_engine_google'")
    conn.rollback()


def test_trigger_refuses_activating_an_uncleared_engine_and_unclearing_the_active_one(conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET active=false WHERE dataset_key='map_engine_leaflet'")
        with pytest.raises(psycopg2.errors.CheckViolation, match="must be cleared before activation"):
            cur.execute("UPDATE dataset_registry SET active=true WHERE dataset_key='map_engine_google'")
    conn.rollback()
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation, match="active engine cannot leave cleared"):
        cur.execute("UPDATE dataset_registry SET license_status='unresolved' WHERE dataset_key='map_engine_leaflet'")
    conn.rollback()
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.CheckViolation, match="only engine rows can be active"):
        cur.execute("UPDATE dataset_registry SET active=true WHERE dataset_key='acs5'")
    conn.rollback()


def test_two_step_swap_inside_one_transaction_succeeds(conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='cleared' WHERE dataset_key='map_engine_google'")
        cur.execute("UPDATE dataset_registry SET active=false WHERE kind='engine'")
        cur.execute("UPDATE dataset_registry SET active=true WHERE dataset_key='map_engine_google' AND kind='engine' AND license_status='cleared'")
        cur.execute("SELECT dataset_key FROM dataset_registry WHERE kind='engine' AND active")
        assert cur.fetchall() == [("map_engine_google",)]
    conn.rollback()


@pytest.mark.parametrize("active_key, expect", [
    ("map_engine_leaflet", {"acs5": True, "esri_tiles": False, "osm_tiles": True, "google_places_live": False, "google_maps_link": True, "practice_locations": False, "map_engine_leaflet": True, "map_engine_google": False}),
    ("map_engine_google",  {"acs5": True, "esri_tiles": False, "osm_tiles": False, "google_places_live": True, "google_maps_link": True, "practice_locations": False, "map_engine_leaflet": False, "map_engine_google": True}),
])
def test_enabled_rule_over_the_matrix(conn, active_key, expect):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='cleared' WHERE dataset_key IN ('map_engine_google','google_places_live')")
        cur.execute("UPDATE dataset_registry SET active=false WHERE kind='engine'")
        cur.execute("UPDATE dataset_registry SET active=true WHERE dataset_key=%s", (active_key,))
    reg = load(conn)
    assert gate.active_engine_name(reg) == gate.engine_name(active_key)
    assert {k: gate.enabled(reg[k], reg) for k in expect} == expect
    conn.rollback()


def test_no_active_engine_falls_back_to_leaflet(conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET active=false WHERE kind='engine'")
    reg = load(conn)
    assert gate.active_engine(reg) is None and gate.active_engine_name(reg) == "leaflet"
    assert gate.enabled(reg["osm_tiles"], reg) is True and gate.enabled(reg["google_places_live"], reg) is False
    conn.rollback()


def test_change_log_is_append_only_for_the_application_role(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO registry_change_log (dataset_key, actor, field, old_value, new_value) VALUES ('map_engine_leaflet','test','active','false','true') RETURNING id")
        rid = cur.fetchone()[0]
        cur.execute("SELECT has_table_privilege(current_user, 'registry_change_log', 'UPDATE'), has_table_privilege(current_user, 'registry_change_log', 'DELETE')")
        assert cur.fetchone() == (False, False)
    conn.rollback()
```
Extend `tests/census/test_registry.py`: add `"map_engine_leaflet", "map_engine_google", "esri_tiles", "places_ui_kit", "google_maps_link", "osm_poi", "google_places_live"` to `SPEC_KEYS`.

**Performance gate (policy §3):** add the `active_engine` entry to `tests/perf/test_query_plans.py::PLANS` — the partial unique index makes the active-engine lookup an index scan; a seq scan on this ~20-row table is tolerated by the test, the assertion is that the query is planned at all after `080` (RED: relation column `active` missing).

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/census/test_map_engines_registry.py tests/census/test_registry.py -q` → FAIL (`column "kind" does not exist`, `AttributeError: kind`).

- [ ] **Step 3: Migration and code**

`migrations/080_map_engines.sql`:
```sql
-- Sub-project 4 (Map engines) — spec §3. Alters the Census registry; adds the decision log.
ALTER TABLE dataset_registry
  ADD COLUMN kind text NOT NULL DEFAULT 'dataset' CHECK (kind IN ('dataset','basemap','engine')),
  ADD COLUMN engines text[] NOT NULL DEFAULT '{leaflet,google}',
  ADD COLUMN active boolean NOT NULL DEFAULT false;

CREATE UNIQUE INDEX dataset_registry_one_active_engine ON dataset_registry ((kind)) WHERE kind = 'engine' AND active;

CREATE OR REPLACE FUNCTION engine_row_rules() RETURNS trigger AS $$
BEGIN
  IF NEW.kind <> 'engine' AND NEW.active THEN
    RAISE EXCEPTION 'only engine rows can be active' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.kind = 'engine' AND NEW.active AND NEW.license_status <> 'cleared' THEN
    RAISE EXCEPTION 'engine % must be cleared before activation', NEW.dataset_key USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.kind = 'engine' AND OLD.active AND NEW.active AND NEW.license_status <> 'cleared' THEN
    RAISE EXCEPTION 'active engine cannot leave cleared; activate another engine first' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER engine_row_rules BEFORE INSERT OR UPDATE ON dataset_registry FOR EACH ROW EXECUTE FUNCTION engine_row_rules();

CREATE TABLE registry_change_log (
  id bigserial PRIMARY KEY,
  dataset_key text NOT NULL REFERENCES dataset_registry(dataset_key),
  changed_at timestamptz NOT NULL DEFAULT now(),
  actor text NOT NULL,
  actor_ip inet,
  actor_ua text,
  field text NOT NULL CHECK (field IN ('license_status','active')),
  old_value text,
  new_value text,
  reason text
);
REVOKE UPDATE, DELETE ON registry_change_log FROM PUBLIC;
REVOKE UPDATE, DELETE ON registry_change_log FROM CURRENT_USER;   -- the migration role is the application role on Railway

-- Engines (the Leaflet row is the approved design and starts active).
INSERT INTO dataset_registry
  (dataset_key, display_name, api_dataset_id, base_url, vintage, naics_param, refresh_cadence, license_status, license_name, license_url, attribution_text, notes, kind, engines, active) VALUES
  ('map_engine_leaflet','Map engine — Leaflet + Esri tiles',NULL,'vendored leaflet@1.9.4','1.9.4',NULL,'static','cleared','BSD-2-Clause','https://github.com/Leaflet/Leaflet/blob/main/LICENSE','Leaflet','Approved design. Tiles are licensed by their own rows (esri_tiles, osm_tiles, imagery).','engine','{leaflet}',true),
  ('map_engine_google','Map engine — Google Maps Platform',NULL,'https://maps.googleapis.com/maps/api/js','weekly',NULL,'live','unresolved','Google Maps Platform Terms','https://cloud.google.com/maps-platform/terms','Map data ©Google (rendered by the API)','Basemap and satellite. Places content renders on this engine only (Terms §3.2.3(e)). Clear after Google plan Task G1 verification.','engine','{google}',false),
  ('esri_tiles','Base map — Esri World Light Gray (design)',NULL,'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}','live',NULL,'live','unresolved','Esri basemap terms (question open)','https://www.esri.com/en-us/legal/terms/full-master-agreement','Tiles © Esri','Platform spec §9: the approved design ships these URLs; licence question open. Leaflet only (Terms §3.2.3(e)).','basemap','{leaflet}',false),
  ('google_places_live','Google Places — live competitor pins (never stored)',NULL,'https://maps.googleapis.com/maps/api/js (places library)','live',NULL,'live','unresolved','Google Maps Platform Terms + SST §14','https://cloud.google.com/maps-platform/terms/maps-service-terms','Google Maps','Displayed live on the Google map only; nothing persisted; no metric derived from pins (Terms §3.2.3(c)(iv)). Clear after Google plan Task G1.','dataset','{google}',false),
  ('places_ui_kit','Google Places UI Kit (list beside any map)',NULL,'https://maps.googleapis.com/maps/api/js (places UI kit)','live',NULL,'live','unresolved','Google Maps Platform SST §15.1','https://cloud.google.com/maps-platform/terms/maps-service-terms','Google Maps','SST §15.1 permits use with a non-Google map. Clear when billing exists.','dataset','{leaflet,google}',false),
  ('google_maps_link','Open in Google Maps (link)',NULL,'https://www.google.com/maps/search/?api=1','n/a',NULL,'n/a','cleared','Google Maps URLs (no key, not a Core Service)','https://developers.google.com/maps/documentation/urls/get-started','Google Maps','Query built from the D8 visible point / place name only.','dataset','{leaflet,google}',false),
  ('osm_poi','OpenStreetMap amenity=veterinary (cross-check)',NULL,'https://download.geofabrik.de','extract date',NULL,'Monthly','unresolved','ODbL 1.0 (share-alike — counsel)','https://www.openstreetmap.org/copyright','© OpenStreetMap contributors','Coverage cross-check only pending counsel on share-alike.','dataset','{leaflet,google}',false);

UPDATE dataset_registry SET kind='basemap', engines='{leaflet}' WHERE dataset_key IN ('osm_tiles','imagery');
UPDATE dataset_registry SET engines='{google}' WHERE dataset_key = 'google_places_aggregate';
UPDATE dataset_registry SET engines='{}' WHERE dataset_key = 'practice_locations';
```

`app/census/registry.py` — extend `COLUMNS` with `"kind", "engines", "active"` and the dataclass:
```python
COLUMNS = ("dataset_key", "display_name", "api_dataset_id", "base_url", "vintage", "naics_param", "refresh_cadence",
           "license_status", "license_name", "license_url", "attribution_text", "last_verified_at", "notes",
           "kind", "engines", "active")
# … in Dataset, after `notes: str | None`:
    kind: str = "dataset"
    engines: list[str] = field(default_factory=lambda: ["leaflet", "google"])
    active: bool = False
```
(`from dataclasses import dataclass, field`.)

`app/census/gate.py` — append:
```python
ENGINE_PREFIX = "map_engine_"


def engine_name(dataset_key: str) -> str:
    return dataset_key[len(ENGINE_PREFIX):] if dataset_key.startswith(ENGINE_PREFIX) else dataset_key


def active_engine(reg):
    """The cleared, active engine row, or None (spec §3). The unique index guarantees at most one."""
    for row in reg.values():
        if row.kind == "engine" and row.active and row.cleared:
            return row
    return None


def active_engine_name(reg) -> str:
    row = active_engine(reg)
    return engine_name(row.dataset_key) if row else "leaflet"   # server-side fallback: the approved design


def enabled(row, reg) -> bool:
    """The one eligibility rule: cleared, and allowed on the active engine."""
    return row.cleared and active_engine_name(reg) in row.engines
```

- [ ] **Step 4: Run to verify passing**

Run: `poetry run pytest tests/census -q` → all pass (A1's `Dataset(*row)` still works because the new columns are appended).

- [ ] **Step 5: Commit**

```bash
git add migrations/080_map_engines.sql app/census/registry.py app/census/gate.py tests/census/test_map_engines_registry.py tests/census/test_registry.py
git commit -m "feat(map-engines): registry kind/engines/active, one-active-engine rules, change log, eligibility rule

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task M2: Shell renderer — snapshot, CSP, preload, escaped config, ETag, `X-PM-Gate`

**Files:**
- Create: `app/shell.py`, `tests/test_shell.py`
- Modify: `app/static.py` (serve the rendered shell), `app/main.py` (`X-PM-Gate` middleware), `app/config.py` (three settings), `app/api/access.py` (add `has_member_session`)

**Interfaces:**
- Consumes: `registry.load`, `gate.active_engine_name`, `gate.enabled`, `gate.version(r)`, `cache.sync_redis`, `db.sync_conn`, `settings.market_data_public`.
- Produces: `shell.Snapshot(engine: str, gate: int, enabled_keys: frozenset[str], csp: str, taken_at: float)`; `shell.snapshot(now: float | None = None) -> Snapshot` (15 s TTL, never raises — falls back to the last snapshot, else a Leaflet default); `shell.reset()` (tests); `shell.CSP_HOSTS: dict[str, dict[str, list[str]]]`; `shell.build_csp(enabled_keys) -> str`; `shell.escape_json(obj) -> str`; `shell.engine_chunks(dist: Path) -> dict[str, str]` (`{"leaflet": "/_app/engine-leaflet-3f9c.js", …}`); `shell.render_index(index_html: str, snap: Snapshot, chunks: dict[str, str], authed: bool) -> str`; `shell.etag(snap, chunks, authed) -> str`; `shell.validate_basemap_host(url: str) -> bool`; `access.has_member_session(request) -> bool` (SP2 replaces the body; until then `settings.market_data_public`); settings `google_maps_browser_key: str | None`, `google_maps_map_id: str | None`, `admin_activate_enabled: bool` (default `settings.environment != "production"`).

- [ ] **Step 1: Failing tests**

`tests/test_shell.py`:
```python
import json
import time
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from app import shell
from app.config import settings
from app.main import create_app


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    d = tmp_path / "dist"; (d / "_app").mkdir(parents=True)
    (d / "index.html").write_text("<!doctype html><html><head><title>x</title></head><body><div id=\"app\"></div></body></html>")
    (d / "_app" / "index-abc123.js").write_text("console.log(1)")
    (d / "_app" / "engine-leaflet-3f9c.js").write_text("export default 1")
    (d / "_app" / "engine-google-91ab.js").write_text("export default 2")
    return d


@pytest.fixture
async def client(dist, scratch_dsn, monkeypatch):
    monkeypatch.setattr(settings, "database_url", scratch_dsn)
    shell.reset()
    async with httpx.AsyncClient(transport=ASGITransport(app=create_app(dist=dist)), base_url="http://test") as c:
        yield c


def test_engine_chunks_are_globbed_once_from_dist(dist):
    assert shell.engine_chunks(dist) == {"leaflet": "/_app/engine-leaflet-3f9c.js", "google": "/_app/engine-google-91ab.js"}


def test_escape_json_cannot_close_the_script_tag():
    out = shell.escape_json({"a": "</script><script>alert(1)</script>", "b": " &"})
    assert "</" not in out and "<" not in out and ">" not in out and "&" not in out and " " not in out
    assert json.loads(out) == {"a": "</script><script>alert(1)</script>", "b": " &"}


def test_csp_is_the_union_of_enabled_rows():
    leaflet = shell.build_csp(frozenset({"map_engine_leaflet", "osm_tiles"}))
    assert "https://*.basemaps.cartocdn.com" in leaflet and "maps.googleapis.com" not in leaflet and "server.arcgisonline.com" not in leaflet
    assert "style-src 'self' 'unsafe-inline'" in leaflet and "img-src 'self' data: blob:" in leaflet
    google = shell.build_csp(frozenset({"map_engine_google", "google_places_live"}))
    assert "script-src 'self' https://maps.googleapis.com" in google and "https://maps.gstatic.com" in google and "cartocdn" not in google
    mixed = shell.build_csp(frozenset({"map_engine_leaflet", "places_ui_kit"}))
    assert "https://maps.googleapis.com" in mixed   # SST §15.1: the UI Kit may sit beside Leaflet


async def test_anonymous_shell_has_config_preload_csp_and_no_key(client, monkeypatch):
    monkeypatch.setattr(settings, "google_maps_browser_key", "browser-k")
    monkeypatch.setattr(settings, "market_data_public", False)
    # `?tab=market` is a legacy no-op after Browse V3 (spec D4): Browse Practices is one
    # screen and always shows market data. The URL is kept here because it is the shape old
    # links take, and it must keep resolving.
    r = await client.get("/browse?tab=market")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache" and r.headers["etag"].startswith('W/"')
    cfg = json.loads(r.text.split('<script id="pm-config" type="application/json">')[1].split("</script>")[0])
    assert cfg == {"engine": "leaflet", "gate": cfg["gate"]} and isinstance(cfg["gate"], int)
    assert '<link rel="modulepreload" href="/_app/engine-leaflet-3f9c.js">' in r.text and "engine-google" not in r.text
    assert "browser-k" not in r.text and "preconnect" not in r.text
    assert "server.arcgisonline.com" not in r.headers["content-security-policy"]   # esri_tiles is unresolved at seed
    assert "https://*.basemaps.cartocdn.com" in r.headers["content-security-policy"]


async def test_authenticated_shell_inlines_google_config_when_google_is_active(client, conn, monkeypatch):
    monkeypatch.setattr(settings, "google_maps_browser_key", "browser-k")
    monkeypatch.setattr(settings, "google_maps_map_id", "practice-match-web")
    monkeypatch.setattr(settings, "market_data_public", True)   # pre-SP2 "authenticated" (QA only)
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='cleared' WHERE dataset_key='map_engine_google'")
        cur.execute("UPDATE dataset_registry SET active=false WHERE kind='engine'")
        cur.execute("UPDATE dataset_registry SET active=true WHERE dataset_key='map_engine_google'")
    conn.commit(); shell.reset()
    r = await client.get("/")
    cfg = json.loads(r.text.split('<script id="pm-config" type="application/json">')[1].split("</script>")[0])
    assert cfg["engine"] == "google" and cfg["google"] == {"mapId": "practice-match-web", "browserKey": "browser-k"}
    assert '<link rel="modulepreload" href="/_app/engine-google-91ab.js">' in r.text and "engine-leaflet" not in r.text
    assert '<link rel="preconnect" href="https://maps.googleapis.com">' in r.text
    assert "https://maps.googleapis.com" in r.headers["content-security-policy"] and "cartocdn" not in r.headers["content-security-policy"]


async def test_etag_304_and_snapshot_ttl(client, monkeypatch):
    r1 = await client.get("/")
    r2 = await client.get("/", headers={"If-None-Match": r1.headers["etag"]})
    assert r2.status_code == 304
    calls = {"n": 0}
    real = shell._load_snapshot
    def counting(*a, **k):
        calls["n"] += 1; return real(*a, **k)
    monkeypatch.setattr(shell, "_load_snapshot", counting)
    shell.reset()
    t0 = time.time()
    shell.snapshot(now=t0); shell.snapshot(now=t0 + 5); shell.snapshot(now=t0 + 14.9)
    assert calls["n"] == 1
    shell.snapshot(now=t0 + 15.1)
    assert calls["n"] == 2


async def test_snapshot_never_raises_and_falls_back_to_leaflet(monkeypatch):
    shell.reset()
    monkeypatch.setattr(shell, "_load_snapshot", lambda: (_ for _ in ()).throw(RuntimeError("db down")))
    snap = shell.snapshot(now=time.time())
    assert snap.engine == "leaflet" and "map_engine_leaflet" in snap.enabled_keys


async def test_api_responses_carry_the_gate_header(client):
    r = await client.get("/api/healthz")
    assert r.headers["x-pm-gate"].isdigit()


def test_every_basemap_base_url_host_is_in_the_csp_allowlist(conn):
    from app.census.registry import load
    for row in load(conn).values():
        if row.kind == "basemap":
            assert shell.validate_basemap_host(row.base_url), row.dataset_key
```

**Performance gate (policy §3):** add `test_render_index_is_string_work_only` to `tests/test_shell.py`: patch `shell._load_snapshot` with a spy, call `shell.render_index(index_html, snap, chunks, authed=False)` 1,000 times from a fixed snapshot, assert the spy was never called and the mean is ≤ 2 ms. RED: `app.shell` missing.

- [ ] **Step 2: Run to verify failure**

Run: `poetry run pytest tests/test_shell.py -q` → FAIL (`ModuleNotFoundError: app.shell`).

- [ ] **Step 3: Implement**

`app/config.py` — add to `Settings`: `google_maps_browser_key: str | None = None`, `google_maps_map_id: str | None = None`, `admin_activate_enabled: bool | None = None` with a property `activate_enabled -> bool` returning `self.admin_activate_enabled if self.admin_activate_enabled is not None else self.environment != "production"`.

`app/api/access.py` — add:
```python
def has_member_session(request: Request) -> bool:
    """SP2 replaces this with the real session check. Until then only the QA evaluation override counts as authenticated."""
    return bool(settings.market_data_public)
```

`app/shell.py`:
```python
"""The SPA shell: server-selected engine, preload hints, per-page CSP, escaped config, ETag (spec §2.3, §4.1, §4.2).
No I/O per request: one snapshot every TTL seconds; chunk names globbed once at start."""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.cache import sync_redis
from app.census import gate
from app.census.registry import load
from app.config import settings
from app.db import sync_conn

log = logging.getLogger(__name__)
TTL = 15.0
GOOGLE_PRECONNECT = ("https://maps.googleapis.com", "https://maps.gstatic.com")

# Hosts each row is allowed to talk to. Union over enabled rows → the page's CSP (spec §4.2).
CSP_HOSTS: dict[str, dict[str, list[str]]] = {
    "map_engine_leaflet":     {"script": [], "img": [], "connect": []},
    "esri_tiles":             {"script": [], "img": ["https://server.arcgisonline.com"], "connect": []},
    "osm_tiles":              {"script": [], "img": ["https://*.basemaps.cartocdn.com"], "connect": []},
    "imagery":                {"script": [], "img": ["https://server.arcgisonline.com"], "connect": []},
    "map_engine_google":      {"script": ["https://maps.googleapis.com"], "img": ["https://maps.gstatic.com", "https://*.googleapis.com", "https://*.ggpht.com"], "connect": ["https://maps.googleapis.com", "https://places.googleapis.com"]},
    "google_places_live":     {"script": ["https://maps.googleapis.com"], "img": ["https://maps.gstatic.com", "https://*.googleapis.com", "https://*.ggpht.com"], "connect": ["https://maps.googleapis.com", "https://places.googleapis.com"]},
    "places_ui_kit":          {"script": ["https://maps.googleapis.com"], "img": ["https://maps.gstatic.com", "https://*.googleapis.com"], "connect": ["https://maps.googleapis.com", "https://places.googleapis.com"]},
}
BASEMAP_HOSTS = {"server.arcgisonline.com", "basemaps.cartocdn.com", "maps.googleapis.com"}


@dataclass(frozen=True)
class Snapshot:
    engine: str
    gate: int
    enabled_keys: frozenset[str]
    csp: str
    taken_at: float


_current: Snapshot | None = None
_DEFAULT = Snapshot("leaflet", 0, frozenset({"map_engine_leaflet", "osm_tiles", "google_maps_link"}), "", 0.0)


def build_csp(enabled_keys: frozenset[str]) -> str:
    script, img, connect = {"'self'"}, {"'self'", "data:", "blob:"}, {"'self'"}
    for key in sorted(enabled_keys):
        hosts = CSP_HOSTS.get(key)
        if hosts:
            script.update(hosts["script"]); img.update(hosts["img"]); connect.update(hosts["connect"])
    order = lambda s: sorted(s, key=lambda h: (not h.startswith("'"), h))  # noqa: E731 — quoted keywords first
    return (f"default-src 'self'; script-src {' '.join(order(script))}; img-src {' '.join(order(img))}; "
            f"connect-src {' '.join(order(connect))}; style-src 'self' 'unsafe-inline'; font-src 'self' data:; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'")


def validate_basemap_host(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return any(host == h or host.endswith("." + h) for h in BASEMAP_HOSTS)


def _load_snapshot() -> Snapshot:
    r = sync_redis()
    conn = sync_conn()
    try:
        reg = load(conn)
    finally:
        conn.close()
    enabled = frozenset(k for k, row in reg.items() if gate.enabled(row, reg))
    engine = gate.active_engine_name(reg)
    return Snapshot(engine, gate.version(r), enabled, build_csp(enabled), time.time())


def snapshot(now: float | None = None) -> Snapshot:
    """Never raises: on failure keeps the last snapshot, else the Leaflet default (spec §9)."""
    global _current
    now = time.time() if now is None else now
    if _current is not None and now - _current.taken_at < TTL:
        return _current
    try:
        snap = _load_snapshot()
        _current = Snapshot(snap.engine, snap.gate, snap.enabled_keys, snap.csp, now)
    except Exception as e:  # noqa: BLE001 — the shell must render regardless
        log.warning("shell snapshot failed: %s", type(e).__name__)
        if _current is None:
            _current = Snapshot(_DEFAULT.engine, _DEFAULT.gate, _DEFAULT.enabled_keys, build_csp(_DEFAULT.enabled_keys), now)
        else:
            _current = Snapshot(_current.engine, _current.gate, _current.enabled_keys, _current.csp, now)
    return _current


def reset() -> None:
    global _current
    _current = None


def engine_chunks(dist: Path) -> dict[str, str]:
    out = {}
    for f in sorted((dist / "_app").glob("engine-*.js")):
        out[f.name.split("-")[1]] = f"/_app/{f.name}"
    return out


def escape_json(obj) -> str:
    s = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    for ch, esc in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), (" ", "\\u2028"), (" ", "\\u2029")):
        s = s.replace(ch, esc)
    return s


def render_index(index_html: str, snap: Snapshot, chunks: dict[str, str], authed: bool) -> str:
    cfg: dict = {"engine": snap.engine, "gate": snap.gate}
    tags = [f'<script id="pm-config" type="application/json">{"{}"}</script>']
    if snap.engine in chunks:
        tags.append(f'<link rel="modulepreload" href="{chunks[snap.engine]}">')
    if snap.engine == "google":
        tags.extend(f'<link rel="preconnect" href="{h}">' for h in GOOGLE_PRECONNECT)
        if authed and settings.google_maps_browser_key and settings.google_maps_map_id:
            cfg["google"] = {"mapId": settings.google_maps_map_id, "browserKey": settings.google_maps_browser_key}
    tags[0] = f'<script id="pm-config" type="application/json">{escape_json(cfg)}</script>'
    return index_html.replace("</head>", "\n".join(tags) + "\n</head>", 1)


def etag(snap: Snapshot, chunks: dict[str, str], authed: bool) -> str:
    h = hashlib.sha1(f"{sorted(chunks.items())}|{snap.engine}|{snap.gate}|{authed}".encode()).hexdigest()[:16]
    return f'W/"{h}"'
```

`app/static.py` — replace the two `index.html` responses with the rendered shell:
```python
from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from app import shell
from app.api.access import has_member_session

# in mount_spa(), after computing root:
    index_html = (root / "index.html").read_text(encoding="utf-8")
    chunks = shell.engine_chunks(root)

    def render(request: Request) -> Response:
        snap = shell.snapshot()
        authed = has_member_session(request)
        tag = shell.etag(snap, chunks, authed)
        headers = {**INDEX_HEADERS, "ETag": tag, "Content-Security-Policy": snap.csp, "Vary": "Cookie"}
        if request.headers.get("if-none-match") == tag:
            return Response(status_code=304, headers=headers)
        return HTMLResponse(shell.render_index(index_html, snap, chunks, authed), headers=headers)

    @app.get("/", include_in_schema=False)
    async def index(request: Request) -> Response:
        return render(request)

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str, request: Request) -> Response:
        candidate = (root / path).resolve()
        if candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate, headers=FILE_HEADERS)
        return render(request)
```
(`tests/test_static.py`'s existing assertions — `id="app"`, `no-cache`, deep-link fallback — still hold; its `dist` fixture needs no `engine-*.js` because `engine_chunks` returns `{}` and `render_index` then emits no preload.)

`app/main.py` — inside `create_app`, after `robots_header`:
```python
    @app.middleware("http")
    async def gate_header(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["X-PM-Gate"] = str(shell.snapshot().gate)
        return response
```
with `from app import shell`.

- [ ] **Step 4: Run to verify passing**

Run: `poetry run pytest tests/test_shell.py tests/test_static.py tests/test_health.py -q` → pass.

- [ ] **Step 5: Commit**

```bash
git add app/shell.py app/static.py app/main.py app/config.py app/api/access.py tests/test_shell.py
git commit -m "feat(shell): server-selected engine, preload, per-page CSP, escaped config, ETag, X-PM-Gate

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task M3: `GET /api/map-config` and the `/api/layers` eligibility rule

**Files:**
- Create: `app/api/map_config.py`, `tests/api/test_map_config.py`
- Modify: `app/api/market.py` (`layers`), `tests/api/test_market_api.py` (response shape), `app/main.py` (router)

**Interfaces:**
- Consumes: `shell.snapshot`, `gate.enabled`, `market._registry` (extend it to select `kind, engines, active`), `access.market_access`, `LAYERS` (Census B5).
- Produces: `GET /api/map-config` → `{"engine": str, "gate": int, "leaflet": {"tiles": str, "labels": str, "attribution": str}}` or `{"engine": "google", "gate": int, "google": {"mapId": str, "browserKey": str}}`; `GET /api/layers` → `{"engine": str, "gate": int, "layers": [ {…, "engines": list[str], "enabled": bool} ]}`.

- [ ] **Step 1: Failing tests**

`tests/api/test_map_config.py` (Census plan `client`, `conn` fixtures; `market_data_public` true → open access, as the Census tests do):
```python
from app import shell
from app.config import settings


async def test_map_config_leaflet_by_default(client):
    r = await client.get("/api/map-config")
    body = r.json()
    assert r.status_code == 200 and body["engine"] == "leaflet" and isinstance(body["gate"], int)
    assert body["leaflet"]["tiles"].startswith("https://") and "attribution" in body["leaflet"] and "google" not in body


async def test_map_config_google_when_active(client, conn, monkeypatch):
    monkeypatch.setattr(settings, "google_maps_browser_key", "browser-k"); monkeypatch.setattr(settings, "google_maps_map_id", "practice-match-web")
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='cleared' WHERE dataset_key='map_engine_google'")
        cur.execute("UPDATE dataset_registry SET active=false WHERE kind='engine'")
        cur.execute("UPDATE dataset_registry SET active=true WHERE dataset_key='map_engine_google'")
    conn.commit(); shell.reset()
    body = (await client.get("/api/map-config")).json()
    assert body["engine"] == "google" and body["google"] == {"mapId": "practice-match-web", "browserKey": "browser-k"} and "leaflet" not in body


async def test_map_config_requires_access(client, monkeypatch):
    monkeypatch.setattr(settings, "market_data_public", False)
    assert (await client.get("/api/map-config")).status_code == 401


async def test_layers_carry_engine_gate_and_engines_and_apply_the_rule(client, conn):
    body = (await client.get("/api/layers")).json()
    assert body["engine"] == "leaflet" and isinstance(body["gate"], int)
    layers = {l["key"]: l for l in body["layers"]}
    assert layers["competition"]["engines"] == ["leaflet", "google"] and layers["competition"]["enabled"] is True
    assert layers["competition_live_points"]["engines"] == ["google"] and layers["competition_live_points"]["enabled"] is False
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status='cleared' WHERE dataset_key IN ('map_engine_google','google_places_live')")
        cur.execute("UPDATE dataset_registry SET active=false WHERE kind='engine'")
        cur.execute("UPDATE dataset_registry SET active=true WHERE dataset_key='map_engine_google'")
    conn.commit(); shell.reset()
    body = (await client.get("/api/layers")).json()
    layers = {l["key"]: l for l in body["layers"]}
    assert body["engine"] == "google" and layers["competition_live_points"]["enabled"] is True and layers["competition"]["enabled"] is True
```

**Performance gate (policy §3):** extend `tests/perf/test_api_latency.py::BUDGET_MS` with `'/api/map-config': 100`; the `/api/layers` budget (100 ms) must still hold with the eligibility rule applied.

- [ ] **Step 2: Run to verify failure** — `poetry run pytest tests/api/test_map_config.py -q` → FAIL (404 / KeyError `engine`).

- [ ] **Step 3: Implement**

`app/api/map_config.py`:
```python
from fastapi import APIRouter, Depends

from app import shell
from app.api.access import market_access
from app.config import settings

router = APIRouter(prefix="/api", dependencies=[Depends(market_access)])
LEAFLET = {
    "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    "labels": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
    "attribution": "Tiles © Esri",
}


@router.get("/map-config")
async def map_config() -> dict:
    snap = shell.snapshot()
    body: dict = {"engine": snap.engine, "gate": snap.gate}
    if snap.engine == "google":
        body["google"] = {"mapId": settings.google_maps_map_id, "browserKey": settings.google_maps_browser_key}
    else:
        body["leaflet"] = LEAFLET
    return body
```
(The Leaflet tile URLs are the design's; when `esri_tiles` is cleared or CARTO is chosen, this constant follows the registry row's `base_url` — Task M9 records that follow-up for SP2's wiring.)

**Basemap licence — one decision record, owned by John and the VIN Foundation.** Esri (the approved design) vs CARTO (the Census spec) is **one** open question, recorded in the Census plan (`docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md`, "Basemap licence — one decision record") and referenced, not restated, here and in CLAUDE.md's "Legally load-bearing" section. Do not swap either way without that decision; attribution stays visible on every map regardless (`attributionControl: true`).

`app/api/market.py` — `_registry` selects `kind, engines, active` too; `layers()` becomes:
```python
LAYERS += [
    {"key": "competition_live_points", "label": "Veterinary practices (Google Maps, live)", "dataset_key": "google_places_live", "metric": None, "is_derived": False, "geo_level": "point",
     "caveat": "Live from Google Maps: the 20 nearest operating veterinary places are shown; practitioner listings at the same address are merged for display. Not stored; not used in any metric."},
    {"key": "competition_live_count", "label": "Veterinary places nearby (Google Maps, live)", "dataset_key": "google_places_aggregate", "metric": None, "is_derived": False, "geo_level": "band",
     "caveat": "Live count of operating veterinary places within the band radius, from Google Maps. The Census establishment count is the official figure used for Low/Moderate/High."},
]


@router.get("/layers")
async def layers() -> dict:
    snap = shell.snapshot()
    with sync_conn() as c:
        reg = registry.load(c)
    async with engine.connect() as conn:
        act = await _active(conn)
    out = []
    for l in LAYERS:
        ds = l["dataset_key"]
        row = reg.get(ds) if ds else None
        enabled = gate.enabled(row, reg) if row else True
        vintage = (f"{act.get('acs5_prior')} → {act.get('acs5')}" if ds == "acs5_prior" else act.get(ds)) if ds else None
        out.append({"key": l["key"], "label": l["label"], "dataset_key": ds, "source_label": row.attribution_text if row else None,
                    "vintage": vintage, "geo_level": l.get("geo_level", "place|catchment" if ds else None), "enabled": enabled,
                    "engines": row.engines if row else ["leaflet", "google"], "is_derived": l["is_derived"], "caveat": l["caveat"]})
    return {"engine": snap.engine, "gate": snap.gate, "layers": out}
```
Register `map_config.router` in `app/main.py` before the catch-all. Update `tests/api/test_market_api.py`: every `layers = {l["key"]: l for l in r.json()}` becomes `… for l in r.json()["layers"]}` and the nine-key assertion becomes `{"income", "pets", "growth", "households", "econ", "competition", "practices", "drive_10", "drive_20", "competition_live_points", "competition_live_count"}`.

- [ ] **Step 4: Run to verify passing** — `poetry run pytest tests/api -q` → pass.

- [ ] **Step 5: Commit** — `feat(api): map-config endpoint; layers carry engine, gate and per-engine eligibility`.

---

### Task M4: Activation endpoint, change log, `/changes`, CSRF, rate limit

**Files:**
- Create: `app/api/csrf.py`, `tests/census/test_activate.py`
- Modify: `app/api/admin_data_sources.py` (`LIST_SQL` fields; `/license` logging; new routes), `tests/census/test_admin_api.py` (row fields)

**Interfaces:**
- Consumes: `require_operator` (A9 → SP2 admin role), `sync_redis`, `engine` (async SQLAlchemy), `gate.invalidate`, `shell.reset` is **not** called (the 15 s TTL is the contract), `settings.activate_enabled`.
- Produces: `POST /api/admin/data-sources/{key}/activate` → `{"active": key, "changed": bool}`; `GET /api/admin/data-sources/changes?limit=50` → `list[dict]`; `csrf.require_csrf(request)`; `admin_data_sources.RATE_LIMIT = (5, 60)`; `admin_data_sources.actor(request) -> tuple[str, str | None, str | None]` (actor, ip, ua — `"operator"` until SP2 sets `request.state.member_id`).

- [ ] **Step 1: Failing tests**

`tests/census/test_activate.py` (Census `client`, `conn`; `H = {"Authorization": f"Bearer {settings.api_secret_key}"}`):
```python
import pytest

from app.config import settings

H = {"Authorization": f"Bearer {settings.api_secret_key}"}


@pytest.fixture(autouse=True)
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "admin_activate_enabled", True)


async def test_rows_expose_kind_engines_active(client):
    rows = {x["dataset_key"]: x for x in (await client.get("/api/admin/data-sources", headers=H)).json()}
    assert rows["map_engine_leaflet"]["kind"] == "engine" and rows["map_engine_leaflet"]["active"] is True and rows["esri_tiles"]["engines"] == ["leaflet"]


async def test_activate_refuses_uncleared_then_swaps_logs_and_bumps_the_gate(client, conn):
    r = await client.post("/api/admin/data-sources/map_engine_google/activate", headers=H, json={"reason": "evaluate on QA"})
    assert r.status_code == 409
    g0 = (await client.get("/api/layers")).headers["x-pm-gate"]
    await client.post("/api/admin/data-sources/map_engine_google/license", headers=H, json={"status": "cleared", "name": "Google Maps Platform Terms"})
    r = await client.post("/api/admin/data-sources/map_engine_google/activate", headers=H, json={"reason": "evaluate on QA"})
    assert r.status_code == 200 and r.json() == {"active": "map_engine_google", "changed": True}
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_key FROM dataset_registry WHERE kind='engine' AND active"); assert cur.fetchall() == [("map_engine_google",)]
        cur.execute("SELECT dataset_key, field, old_value, new_value, actor, reason FROM registry_change_log ORDER BY id")
        rows = cur.fetchall()
    assert ("map_engine_google", "license_status", "unresolved", "cleared", "operator", None) in rows
    assert ("map_engine_google", "active", "map_engine_leaflet", "map_engine_google", "operator", "evaluate on QA") in rows
    from app.cache import sync_redis
    from app.census import gate
    assert gate.version(sync_redis()) > int(g0)


async def test_activate_is_idempotent(client, conn):
    v = (await client.get("/api/layers")).headers["x-pm-gate"]
    r = await client.post("/api/admin/data-sources/map_engine_leaflet/activate", headers=H, json={})
    assert r.json() == {"active": "map_engine_leaflet", "changed": False}
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM registry_change_log WHERE field='active'"); assert cur.fetchone()[0] == 0
    assert (await client.get("/api/layers")).headers["x-pm-gate"] == v


async def test_activate_rejects_non_engine_rows_disabled_environments_and_rate(client, monkeypatch):
    assert (await client.post("/api/admin/data-sources/acs5/activate", headers=H, json={})).status_code == 409
    monkeypatch.setattr(settings, "admin_activate_enabled", False)
    assert (await client.post("/api/admin/data-sources/map_engine_leaflet/activate", headers=H, json={})).status_code == 403
    monkeypatch.setattr(settings, "admin_activate_enabled", True)
    codes = [(await client.post("/api/admin/data-sources/map_engine_leaflet/activate", headers=H, json={})).status_code for _ in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


async def test_changes_lists_newest_first(client):
    await client.post("/api/admin/data-sources/imagery/license", headers=H, json={"status": "blocked"})
    rows = (await client.get("/api/admin/data-sources/changes?limit=5", headers=H)).json()
    assert rows[0]["dataset_key"] == "imagery" and rows[0]["field"] == "license_status" and rows[0]["new_value"] == "blocked"


async def test_csrf_double_submit_for_cookie_sessions_bearer_exempt(client):
    # bearer: exempt
    assert (await client.post("/api/admin/data-sources/map_engine_leaflet/activate", headers=H, json={})).status_code == 200
    # cookie session without token: refused before auth runs (SP2 wires the real session; the stub treats any pm_session cookie as a session)
    r = await client.post("/api/admin/data-sources/map_engine_leaflet/activate", cookies={"pm_session": "s", "pm_csrf": "t"}, json={})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "CSRF"
```

- [ ] **Step 2: Run to verify failure** — `poetry run pytest tests/census/test_activate.py -q` → FAIL (404 on `/activate`).

- [ ] **Step 3: Implement**

`app/api/csrf.py`:
```python
"""Double-submit CSRF for cookie sessions (SP2). Bearer-token callers (the pre-SP2 operator) have no ambient credential and are exempt."""
from fastapi import HTTPException, Request


def require_csrf(request: Request) -> None:
    if request.headers.get("authorization", "").startswith("Bearer "):
        return
    if "pm_session" in request.cookies:
        token = request.headers.get("x-csrf-token")
        if not token or token != request.cookies.get("pm_csrf"):
            raise HTTPException(403, detail={"code": "CSRF", "message": "missing or mismatched X-CSRF-Token"})
```

`app/api/admin_data_sources.py` — additions (router dependencies become `[Depends(require_csrf), Depends(require_operator)]` in that order so the CSRF test sees 403 before 401):
```python
from fastapi import HTTPException, Request
from pydantic import BaseModel

from app.api.csrf import require_csrf
from app.config import settings

RATE_LIMIT = (5, 60)
LIST_SQL = text("""SELECT r.dataset_key, r.display_name, r.api_dataset_id, r.vintage, r.refresh_cadence, r.license_status, r.license_name, r.license_url,
       r.attribution_text, r.last_verified_at, r.notes, r.drift_flagged, r.kind, r.engines, r.active, a.vintage AS active_vintage,
       (SELECT json_build_object('status', i.status, 'finished_at', i.finished_at, 'rows_written', i.rows_written)
          FROM ingest_run i WHERE i.dataset_key = r.dataset_key ORDER BY i.id DESC LIMIT 1) AS last_run
FROM dataset_registry r LEFT JOIN active_vintage a USING (dataset_key) ORDER BY r.dataset_key""")


def actor(request: Request) -> tuple[str, str | None, str | None]:
    who = getattr(request.state, "member_id", None) or "operator"
    return str(who), request.client.host if request.client else None, request.headers.get("user-agent")


LOG_SQL = text("""INSERT INTO registry_change_log (dataset_key, actor, actor_ip, actor_ua, field, old_value, new_value, reason)
                  VALUES (:k, :a, CAST(:ip AS inet), :ua, :f, :o, :n, :r)""")


class Activation(BaseModel):
    reason: str | None = None


@router.post("/data-sources/{dataset_key}/activate")
async def activate(dataset_key: str, body: Activation, request: Request) -> dict:
    if not settings.activate_enabled:
        raise HTTPException(403, detail={"code": "ACTIVATE_DISABLED", "message": "engine activation is disabled in this environment until SP2 ships"})
    r = sync_redis()
    bucket = f"admin:activate:{int(__import__('time').time()) // RATE_LIMIT[1]}"
    n = r.incr(bucket); r.expire(bucket, RATE_LIMIT[1])
    if n > RATE_LIMIT[0]:
        raise HTTPException(429, detail={"code": "RATE_LIMITED", "message": "at most 5 activations per minute"})
    who, ip, ua = actor(request)
    async with engine.begin() as conn:
        cur = (await conn.execute(text("SELECT dataset_key FROM dataset_registry WHERE kind='engine' AND active FOR UPDATE"))).scalar()
        target = (await conn.execute(text("SELECT kind, license_status FROM dataset_registry WHERE dataset_key=:k FOR UPDATE"), {"k": dataset_key})).mappings().first()
        if not target or target["kind"] != "engine" or target["license_status"] != "cleared":
            raise HTTPException(409, detail={"code": "NOT_ACTIVATABLE", "message": f"{dataset_key} is not a cleared engine row"})
        if cur == dataset_key:
            return {"active": dataset_key, "changed": False}
        await conn.execute(text("UPDATE dataset_registry SET active=false WHERE kind='engine'"))
        res = await conn.execute(text("UPDATE dataset_registry SET active=true WHERE dataset_key=:k AND kind='engine' AND license_status='cleared'"), {"k": dataset_key})
        if res.rowcount != 1:
            raise HTTPException(409, detail={"code": "NOT_ACTIVATABLE", "message": dataset_key})
        await conn.execute(LOG_SQL, {"k": dataset_key, "a": who, "ip": ip, "ua": ua, "f": "active", "o": cur, "n": dataset_key, "r": body.reason})
    gate.invalidate(sync_redis(), dataset_key)
    return {"active": dataset_key, "changed": True}


@router.get("/data-sources/changes")
async def changes(limit: int = 50) -> list[dict]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text("SELECT id, dataset_key, changed_at, actor, actor_ip::text AS actor_ip, actor_ua, field, old_value, new_value, reason "
                                        "FROM registry_change_log ORDER BY id DESC LIMIT :n"), {"n": min(max(limit, 1), 200)})).mappings().all()
    return [dict(r) for r in rows]
```
In `decide_license`, read the old status first (`SELECT license_status … FOR UPDATE`), and after the UPDATE insert `LOG_SQL` with `f='license_status'`, `o=old`, `n=body.status`, `r=body.notes` and the `actor(request)` triple (add `request: Request` to its signature). The `/changes` route must be declared **before** `/{dataset_key}/license` so it is not captured as a key.

- [ ] **Step 4: Run to verify passing** — `poetry run pytest tests/census/test_activate.py tests/census/test_admin_api.py -q` → pass.

- [ ] **Step 5: Commit** — `feat(admin): engine activation (transactional, idempotent, rate-limited, CSRF), change log, /changes`.

---

### Task M5: Frontend — shell config, one-engine import, `GoogleMapEngine`, shared host, gate watcher, eligibility

> **Rebase note (Browse V3, spec D4).** This task lands **after** the Browse V3 sub-project.
> `engine.ts` by then already carries `AreaStyle`, `RingStyle`, `TooltipSpec`, `Handle.openTooltip`,
> `rectangle(bounds, style, group, tooltip?, onClick?)`, `ring(center, radiusM, style, group)` and `panInside(pos, padding)`, and
> `MarketMapView.vue` is the V3 port (community mosaic shading on one shared canvas renderer,
> `rf-tip`/`rf-callout`, one dashed 16 km ring, `scaleControl: false`). `GoogleMapEngine`
> must implement `rectangle`, `ring` and `panInside` too, and `engines/contract.test.ts` must
> cover them for both engines. `ListingsMap.vue` (deleted in Browse V3) is the V2-era listings
> map component this task's file list used to name; it no longer exists.
>
> Browse V3 also restyled every display-size heading (V3 drops `text-transform: uppercase` and
> its letter-spacing on all 26; micro labels keep theirs), so every visual baseline in
> `frontend/tests/visual.spec.ts-snapshots/` was regenerated from the V3 design in Browse V3
> Task V9 — including the screens the V3 bundle listed as untouched. There is no pre-V3 pixel
> oracle to compare against any more; the V3 reference is the oracle.
>
> Amended 2026-09-07: Task V13 restored V2's typography through local amendment A1 (Browse V3 spec D15/D16); the thirteen non-Browse screens are byte-identical to V2 again, so a pre-V3 pixel oracle exists for them. Browse-only elements keep V3's type.

**Files:**
- Create: `frontend/src/map/config.ts`, `frontend/src/map/gate.ts`, `frontend/src/map/host.ts`, `frontend/src/map/eligibility.ts`, `frontend/src/map/engines/google.ts`, `frontend/src/map/engines/google-loader.ts`, `frontend/src/map/engines/google.css`, `frontend/src/map/testing/google-stub.ts`, tests `config.test.ts`, `gate.test.ts`, `host.test.ts`, `eligibility.test.ts`, `engines/google.test.ts`, `engines/contract.test.ts`
- Modify: `frontend/src/map/create.ts` (config-driven), `frontend/vite.config.ts` (`manualChunks`, `build.manifest`), `frontend/src/components/MarketMapView.vue` (use `useMapHost()`), `frontend/src/main.ts` (`installGateWatcher(router)`), `frontend/src/map/boundary.test.ts` (allow the Google loader in `engines/`)

**Interfaces:**
- Consumes: `MapEngine`, `MountOptions`, `MarkerOptions`, `CircleStyle`, `LatLng`, `BaseKind` from `frontend/src/map/engine.ts` and `LeafletMapEngine` (Platform Task 1b); `router` from Platform Task 2.
- Produces: `ShellConfig { engine: 'leaflet' | 'google'; gate: number; leaflet?: { tiles: string; labels: string; attribution: string }; google?: { mapId: string; browserKey: string } }`; `readShellConfig(): ShellConfig | null`; `fetchMapConfig(): Promise<ShellConfig>`; `createEngine(cfg: ShellConfig): Promise<MapEngine>`; `useMapHost(): { attach(el: HTMLElement, opts: MountOptions): Promise<MapEngine>; detach(): void; engine(): MapEngine | null }`; `apiFetch(input, init?)`, `gateChanged(): boolean`, `installGateWatcher(router, onEngineChange: () => void)`; `enabledFor(layer: { enabled: boolean; engines: string[] }, mounted: 'leaflet' | 'google'): boolean`; `GoogleMapEngine`; `makeGoogleStub(nearby?)`.

- [ ] **Step 1: Failing tests**

`frontend/src/map/config.test.ts`:
```ts
// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { fetchMapConfig, readShellConfig } from './config';

describe('shell config', () => {
  it('reads the server-rendered JSON and returns null when absent', () => {
    document.head.innerHTML = '<script id="pm-config" type="application/json">{"engine":"google","gate":7,"google":{"mapId":"m","browserKey":"k"}}</script>';
    expect(readShellConfig()).toEqual({ engine: 'google', gate: 7, google: { mapId: 'm', browserKey: 'k' } });
    document.head.innerHTML = '';
    expect(readShellConfig()).toBeNull();
  });
  it('fetches /api/map-config with credentials', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ engine: 'leaflet', gate: 1, leaflet: { tiles: 't', labels: 'l', attribution: 'a' } }), { headers: { 'X-PM-Gate': '1' } }));
    vi.stubGlobal('fetch', f);
    expect((await fetchMapConfig()).engine).toBe('leaflet');
    expect(f).toHaveBeenCalledWith('/api/map-config', expect.objectContaining({ credentials: 'same-origin' }));
  });
});
```

`frontend/src/map/gate.test.ts`:
```ts
// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { apiFetch, gateChanged, resetGate, installGateWatcher } from './gate';

describe('gate watcher', () => {
  it('detects a changed X-PM-Gate across responses and refetches config only on route change', async () => {
    resetGate(3);
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { headers: { 'X-PM-Gate': '4' } })));
    await apiFetch('/api/layers');
    expect(gateChanged()).toBe(true);
    const hooks: Array<() => Promise<void>> = [];
    const router = { afterEach: (cb: () => Promise<void>) => hooks.push(cb) };
    const onEngineChange = vi.fn();
    const fetchCfg = vi.fn(async () => ({ engine: 'google' as const, gate: 4 }));
    installGateWatcher(router as never, onEngineChange, { current: () => ({ engine: 'leaflet' as const, gate: 3 }), fetchCfg });
    expect(fetchCfg).not.toHaveBeenCalled();          // no polling, no eager fetch
    await hooks[0]();
    expect(fetchCfg).toHaveBeenCalledTimes(1);
    expect(onEngineChange).toHaveBeenCalledWith({ engine: 'google', gate: 4 });
    expect(gateChanged()).toBe(false);
  });
});
```

`frontend/src/map/eligibility.test.ts`:
```ts
import { describe, expect, it } from 'vitest';
import { enabledFor } from './eligibility';

describe('enabledFor', () => {
  it('requires the server flag and the mounted engine to be allowed', () => {
    expect(enabledFor({ enabled: true, engines: ['leaflet', 'google'] }, 'leaflet')).toBe(true);
    expect(enabledFor({ enabled: true, engines: ['google'] }, 'leaflet')).toBe(false);   // a stale client never draws Google content on Leaflet
    expect(enabledFor({ enabled: false, engines: ['leaflet', 'google'] }, 'google')).toBe(false);
  });
});
```

`frontend/src/map/engines/contract.test.ts` — one suite, two engines:
```ts
// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import type { MapEngine } from '../engine';
import { LeafletMapEngine } from './leaflet';
import { GoogleMapEngine } from './google';
import { installLeafletStub } from '../testing/leaflet-stub';
import { makeGoogleStub } from '../testing/google-stub';

const cases: Array<[string, () => MapEngine]> = [
  ['leaflet', () => { installLeafletStub(); return new LeafletMapEngine(); }],
  ['google', () => new GoogleMapEngine({ g: makeGoogleStub().g, mapId: 'practice-match-web' })],
];

describe.each(cases)('MapEngine contract — %s', (name, make) => {
  it('mounts, marks the element, draws and clears by group, switches base, reports moves', async () => {
    vi.useFakeTimers();
    const engine = make(); const el = document.createElement('div'); document.body.appendChild(el);
    await engine.mount(el, { center: [30.31, -97.75], zoom: 10, basemap: 'map', zoomControl: 'bottomright', scaleControl: false });
    expect(el.dataset.map).toBe(name);
    engine.circle([30.3, -97.7], 8000, { fillColor: '#003a70', fillOpacity: 0.2 }, 'overlay');
    const h = engine.marker([30.3, -97.7], { html: '<div class="dot"></div>', size: [20, 20], anchor: [10, 10], tooltip: 'Cedar Park — $118K' }, 'overlay');
    expect(el.querySelector('.dot')).not.toBeNull();
    h.remove(); expect(el.querySelector('.dot')).toBeNull();
    engine.marker([30.3, -97.7], { html: '<div class="pin"></div>', size: [72, 26], anchor: [36, 13], onClick: () => {} }, 'pins');
    engine.clear('pins'); expect(el.querySelector('.pin')).toBeNull();
    engine.setBase('satellite'); engine.setBase('map');
    const moves: number[] = []; const off = engine.onMove((_c, z) => moves.push(z));
    engine.setView([30.5, -97.8], 12); expect(engine.getZoom()).toBe(12);
    off(); engine.show(); engine.destroy();
    vi.useRealTimers();
  });
});
```

`frontend/src/map/engines/google.test.ts` (Google-specific behaviour):
```ts
// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { GoogleMapEngine } from './google';
import { makeGoogleStub } from '../testing/google-stub';

describe('GoogleMapEngine', () => {
  it('passes the Map ID, disables default UI but keeps zoom control when asked, maps satellite to hybrid', async () => {
    const { g, Map } = makeGoogleStub(); const el = document.createElement('div');
    const engine = new GoogleMapEngine({ g, mapId: 'practice-match-web' });
    await engine.mount(el, { center: [30.31, -97.75], zoom: 10, basemap: 'satellite', zoomControl: 'bottomright', scaleControl: true });
    const m = Map.instances[0];
    expect(m.opts).toMatchObject({ mapId: 'practice-match-web', disableDefaultUI: true, zoomControl: true, scaleControl: true, clickableIcons: false, gestureHandling: 'greedy' });
    expect(m.typeId).toBe('hybrid');
    engine.setBase('map'); expect(m.typeId).toBe('roadmap');
    expect(el.dataset.mapId).toBe('practice-match-web');
  });
  it('renders marker HTML centred on the anchor with the tooltip inside the marker and no coordinates in the DOM', async () => {
    const { g } = makeGoogleStub(); const el = document.createElement('div');
    const engine = new GoogleMapEngine({ g, mapId: 'm' });
    await engine.mount(el, { center: [30.31, -97.75], zoom: 10, basemap: 'map' });
    engine.marker([30.5, -97.8], { html: '<div class="dot"></div>', size: [20, 20], anchor: [10, 10], tooltip: 'Cedar Park — 7 veterinary establishments' }, 'overlay');
    const wrap = el.querySelector('.gm-vf-marker') as HTMLElement;
    expect(wrap.style.transform).toBe('translate(0px, 10px)');
    expect(wrap.querySelector('.gm-vf-tip')?.textContent).toBe('Cedar Park — 7 veterinary establishments');
    expect(el.innerHTML).not.toMatch(/30\.5|-97\.8/);
  });
});
```

`frontend/src/map/host.test.ts`:
```ts
// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { useMapHost, __resetHost } from './host';

describe('useMapHost', () => {
  it('creates one engine, re-parents it between hosts and calls show() instead of mounting again', async () => {
    __resetHost();
    const engine = { mount: vi.fn(async (el: HTMLElement) => { el.dataset.map = 'leaflet'; }), show: vi.fn(), setView: vi.fn(), destroy: vi.fn(), name: 'leaflet' };
    const create = vi.fn(async () => engine);
    const host = useMapHost({ create });
    const a = document.createElement('div'); const b = document.createElement('div');
    await host.attach(a, { center: [30, -97], zoom: 10, basemap: 'map' });
    host.detach();
    await host.attach(b, { center: [31, -98], zoom: 11, basemap: 'map' });
    expect(create).toHaveBeenCalledTimes(1); expect(engine.mount).toHaveBeenCalledTimes(1);
    expect(b.firstElementChild?.getAttribute('data-map')).toBe('leaflet');   // the same map element moved into b
    expect(engine.show).toHaveBeenCalledTimes(1); expect(engine.setView).toHaveBeenCalledWith([31, -98], 11, false);
  });
});
```

Extend `frontend/src/map/boundary.test.ts` (Platform Task 1b) so that `maps.googleapis.com` and `google.maps` strings are allowed only in `src/map/engines/` and `src/map/testing/`.

**Performance gate (policy §3):** `frontend/tests/bundle-budget.test.ts` (Platform Task 1) now finds `engine-leaflet-*` and `engine-google-*` and enforces ≤ 60 KB and ≤ 12 KB gz, and first-load JS ≤ 300 KB gz. RED until `manualChunks` lands; GREEN after Step 3.

- [ ] **Step 2: Run to verify failure** — `cd frontend && npx vitest run src/map` → FAIL (missing modules).

- [ ] **Step 3: Implement**

`frontend/src/map/config.ts`:
```ts
export interface ShellConfig { engine: 'leaflet' | 'google'; gate: number; leaflet?: { tiles: string; labels: string; attribution: string }; google?: { mapId: string; browserKey: string } }

export function readShellConfig(): ShellConfig | null {
  const el = document.getElementById('pm-config');
  if (!el?.textContent) return null;
  try { return JSON.parse(el.textContent) as ShellConfig; } catch { return null; }
}

export async function fetchMapConfig(): Promise<ShellConfig> {
  const r = await fetch('/api/map-config', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
  if (!r.ok) throw new Error(`map-config ${r.status}`);
  return (await r.json()) as ShellConfig;
}
```

`frontend/src/map/gate.ts`:
```ts
import type { ShellConfig } from './config';
import { fetchMapConfig } from './config';

let seen: number | null = null; let changed = false;
export function resetGate(v: number | null = null) { seen = v; changed = false; }
export function gateChanged() { return changed; }

/** Every API call goes through here so the client learns of a licence/engine decision from responses it was making anyway — no polling. */
export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const r = await fetch(input, { credentials: 'same-origin', ...init });
  const g = r.headers.get('X-PM-Gate');
  if (g !== null) { const n = Number(g); if (seen !== null && n !== seen) changed = true; seen = n; }
  return r;
}

export function installGateWatcher(router: { afterEach: (cb: () => Promise<void>) => void }, onEngineChange: (cfg: ShellConfig) => void,
  deps: { current: () => ShellConfig; fetchCfg: () => Promise<ShellConfig> } = { current: () => currentConfig(), fetchCfg: fetchMapConfig }) {
  router.afterEach(async () => {
    if (!changed) return;
    changed = false;
    const cfg = await deps.fetchCfg();
    setCurrentConfig(cfg);
    if (cfg.engine !== deps.current().engine) onEngineChange(cfg);   // the component re-attaches on its next mount; never mid-view
  });
}

let current: ShellConfig = { engine: 'leaflet', gate: 0 };
export function currentConfig() { return current; }
export function setCurrentConfig(c: ShellConfig) { current = c; }
```

`frontend/src/map/eligibility.ts`:
```ts
/** Defensive twin of the server rule: a component draws a layer only if the server enabled it AND the engine it mounted is allowed. */
export function enabledFor(layer: { enabled: boolean; engines: string[] }, mounted: 'leaflet' | 'google'): boolean {
  return layer.enabled && layer.engines.includes(mounted);
}
```

`frontend/src/map/create.ts` (replaces Task 1b's Leaflet-only version):
```ts
import type { MapEngine } from './engine';
import { fetchMapConfig, readShellConfig, type ShellConfig } from './config';
import { setCurrentConfig } from './gate';

/** Imports exactly one engine module — the one the server chose. The other chunk is never requested. */
export async function createEngine(cfg?: ShellConfig): Promise<MapEngine> {
  let c = cfg ?? readShellConfig() ?? { engine: 'leaflet' as const, gate: 0 };
  if (c.engine === 'google' && !c.google) c = await fetchMapConfig();      // anonymous shell: the key arrives after sign-in
  setCurrentConfig(c);
  if (c.engine === 'google' && c.google) {
    const [{ GoogleMapEngine }, { loadGoogleMaps }] = await Promise.all([import('./engines/google'), import('./engines/google-loader')]);
    return new GoogleMapEngine({ g: await loadGoogleMaps(c.google.browserKey), mapId: c.google.mapId });
  }
  const { LeafletMapEngine } = await import('./engines/leaflet');
  return new LeafletMapEngine();
}
```

`frontend/src/map/host.ts` — the one long-lived instance:
```ts
import type { MapEngine, MountOptions } from './engine';
import { createEngine } from './create';

let engine: MapEngine | null = null; let mapEl: HTMLElement | null = null; let creating: Promise<MapEngine> | null = null;
export function __resetHost() { engine = null; mapEl = null; creating = null; }

export function useMapHost(deps: { create: () => Promise<MapEngine> } = { create: () => createEngine() }) {
  return {
    engine: () => engine,
    async attach(host: HTMLElement, opts: MountOptions): Promise<MapEngine> {
      if (!engine) {
        creating ??= deps.create();
        engine = await creating;
        mapEl = document.createElement('div'); mapEl.style.cssText = 'position:absolute;inset:0;';
        host.appendChild(mapEl);
        await engine.mount(mapEl, opts);
        return engine;
      }
      if (mapEl && mapEl.parentElement !== host) host.appendChild(mapEl);   // re-parent: one billable map load per session
      engine.setView(opts.center, opts.zoom, false);
      engine.setBase(opts.basemap);
      engine.show();
      return engine;
    },
    detach() { mapEl?.remove(); },                                          // keep the instance alive; nothing is destroyed
  };
}
```
(`MountOptions.basemap` is applied on re-attach; per-attach `zoomControl`/`scaleControl` differences (the V3 market map mounts both `false`) are handled by each engine's `setControls(opts)` — add `setControls(opts: Pick<MountOptions, 'zoomControl' | 'scaleControl'>): void` to `MapEngine` in `engine.ts`, implemented in Leaflet by adding/removing `L.control.zoom`/`L.control.scale` and in Google by `map.setOptions({ zoomControl, scaleControl })`; `attach` calls it after `setBase`.)

`frontend/src/map/engines/google-loader.ts`:
```ts
declare global { interface Window { google?: typeof google; __pmMapsReady?: () => void } }
let pending: Promise<typeof google> | null = null;
export function loadGoogleMaps(key: string, version = 'weekly'): Promise<typeof google> {
  if (window.google?.maps && !pending) return Promise.resolve(window.google);
  if (pending) return pending;
  pending = new Promise<typeof google>((resolve, reject) => {
    window.__pmMapsReady = () => resolve(window.google as typeof google);
    const s = document.createElement('script');
    s.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=${encodeURIComponent(version)}&loading=async&callback=__pmMapsReady`;
    s.async = true;
    s.onerror = () => { pending = null; reject(new Error('Google Maps failed to load')); };
    document.head.appendChild(s);
  });
  return pending;
}
```

`frontend/src/map/engines/google.ts`:
```ts
import type { BaseKind, CircleStyle, Handle, LatLng, MapEngine, MarkerOptions, MountOptions } from '../engine';
import './google.css';

export interface GoogleEngineOptions { g: typeof google; mapId: string }

export class GoogleMapEngine implements MapEngine {
  readonly name = 'google' as const;
  private map!: google.maps.Map;
  private readonly groups = new Map<string, Set<{ remove(): void }>>();
  constructor(private readonly o: GoogleEngineOptions) {}

  async mount(el: HTMLElement, opts: MountOptions): Promise<void> {
    const { Map } = (await this.o.g.maps.importLibrary('maps')) as google.maps.MapsLibrary;
    await this.o.g.maps.importLibrary('marker');
    // disableDefaultUI removes controls only; Google's logo, "Map data ©" and Terms link stay as rendered (policy).
    this.map = new Map(el, { center: { lat: opts.center[0], lng: opts.center[1] }, zoom: opts.zoom, mapId: this.o.mapId, disableDefaultUI: true,
      zoomControl: Boolean(opts.zoomControl), scaleControl: Boolean(opts.scaleControl), gestureHandling: 'greedy', clickableIcons: false,
      mapTypeId: opts.basemap === 'satellite' ? 'hybrid' : 'roadmap' });
    el.dataset.map = 'google'; el.dataset.mapId = this.o.mapId;
  }
  show(): void { this.o.g.maps.event.trigger(this.map, 'resize'); }
  setControls(opts: Pick<MountOptions, 'zoomControl' | 'scaleControl'>): void { this.map.setOptions({ zoomControl: Boolean(opts.zoomControl), scaleControl: Boolean(opts.scaleControl) }); }
  setView(c: LatLng, zoom: number): void { this.map.setCenter({ lat: c[0], lng: c[1] }); this.map.setZoom(zoom); }
  getZoom(): number { return this.map.getZoom() ?? 0; }
  zoomIn(): void { this.map.setZoom(this.getZoom() + 1); }
  zoomOut(): void { this.map.setZoom(this.getZoom() - 1); }
  fitBounds(points: LatLng[]): void { const b = new this.o.g.maps.LatLngBounds(); points.forEach((p) => b.extend({ lat: p[0], lng: p[1] })); this.map.fitBounds(b, 24); }
  setBase(kind: BaseKind): void { this.map.setMapTypeId(kind === 'satellite' ? 'hybrid' : 'roadmap'); }
  circle(c: LatLng, radiusM: number, s: CircleStyle, group: string): Handle {
    const circle = new this.o.g.maps.Circle({ map: this.map, center: { lat: c[0], lng: c[1] }, radius: radiusM, strokeWeight: s.stroke ? 1 : 0, strokeColor: s.fillColor, fillColor: s.fillColor, fillOpacity: s.fillOpacity, clickable: Boolean(s.interactive) });
    return this.track(group, { remove: () => circle.setMap(null) });
  }
  marker(pos: LatLng, o: MarkerOptions, group: string): Handle {
    const wrap = document.createElement('div');
    wrap.className = 'gm-vf-marker';
    wrap.style.width = `${o.size[0]}px`; wrap.style.height = `${o.size[1]}px`;
    wrap.style.transform = `translate(${o.size[0] / 2 - o.anchor[0]}px, ${o.size[1] - o.anchor[1]}px)`;   // AdvancedMarker anchors bottom-centre; reproduce the Leaflet iconAnchor
    wrap.innerHTML = o.html;
    if (o.tooltip) { const tip = document.createElement('div'); tip.className = 'gm-vf-tip'; tip.textContent = o.tooltip; wrap.appendChild(tip); }
    const m = new this.o.g.maps.marker.AdvancedMarkerElement({ map: this.map, position: { lat: pos[0], lng: pos[1] }, content: wrap, zIndex: o.zIndexOffset ?? 0, gmpClickable: Boolean(o.onClick) });
    if (o.onClick) m.addListener('gmp-click', o.onClick);
    return this.track(group, { remove: () => { m.map = null; } });
  }
  clear(group: string): void { this.groups.get(group)?.forEach((h) => h.remove()); this.groups.delete(group); }
  onMove(cb: (center: LatLng, zoom: number) => void): () => void {
    const l = this.map.addListener('idle', () => { const c = this.map.getCenter(); if (c) cb([c.lat(), c.lng()], this.getZoom()); });
    return () => l.remove();
  }
  destroy(): void { for (const g of [...this.groups.keys()]) this.clear(g); }
  private track(group: string, h: { remove(): void }): Handle { const set = this.groups.get(group) ?? new Set(); this.groups.set(group, set); set.add(h); return { remove: () => { h.remove(); set.delete(h); } }; }
}
```
`google.css` reproduces Leaflet's tooltip look for the in-marker tip (`.gm-vf-marker{position:relative}.gm-vf-tip{display:none;position:absolute;bottom:calc(100% + 6px);left:50%;transform:translateX(-50%);background:#fff;border:1px solid #fff;border-radius:3px;padding:6px;color:#222;font:12px/1.4 ProximaNova,Arial,Helvetica,sans-serif;box-shadow:0 1px 3px rgba(0,0,0,.4);white-space:nowrap}.gm-vf-marker:hover .gm-vf-tip{display:block}`). `testing/google-stub.ts` is the Google plan's stub extended with `Map.instances`, `event.trigger`, `setOptions`, `AdvancedMarkerElement.addListener`, `zIndex`.

`frontend/vite.config.ts` — add:
```ts
build: { assetsDir: '_app', manifest: true, rollupOptions: { output: { chunkFileNames: '_app/[name]-[hash].js', manualChunks(id) {
  if (id.includes('/src/map/engines/leaflet') || id.includes('/src/lib/leaflet') || id.includes('node_modules/leaflet')) return 'engine-leaflet';
  if (id.includes('/src/map/engines/google')) return 'engine-google';
} } } }
```
Components: `MarketMapView.vue` — the only map component, since `ListingsMap.vue` (deleted in Browse V3) no longer exists — replaces its `createEngine()` call (Task 1b) with `const host = useMapHost(); engine = await host.attach(hostEl, { center, zoom, basemap, zoomControl: false, scaleControl: false }); … onBeforeUnmount(() => host.detach())`. `main.ts`: `installGateWatcher(router, () => { /* next mount re-attaches on the new engine */ __resetHost(); })`.

- [ ] **Step 4: Run to verify passing** — `cd frontend && npx vitest run && npm run build && ls dist/_app | grep -E 'engine-(leaflet|google)-'` → tests pass; both chunks exist; the main bundle contains no `leaflet` and no `maps.googleapis.com` string (`! grep -l 'maps.googleapis.com\|L.tileLayer' dist/_app/index-*.js`).

- [ ] **Step 5: Commit** — `feat(map): config-driven single-engine import, GoogleMapEngine, shared map host, gate watcher, eligibility twin`.

---

### Task M6: Admin Data Sources rows and the two-click Activate (frontend mapping, wired live by SP2)

**Files:**
- Create: `frontend/src/admin/dataSources.ts`, `frontend/src/admin/dataSources.test.ts`

**Interfaces:**
- Consumes: `GET /api/admin/data-sources` rows (Task M4 shape), `POST …/activate`, `apiFetch`.
- Produces: `toDataRows(rows: ApiRow[], ui: ActivateUi): Row[]` in the exact `cell()` shape `logic.js` renders (`hasMain, main, hasSub, sub, hasPill, pill, pillStyle, hasActions, actions[{label, go, style}]`); `useActivate(post: (key: string) => Promise<void>): ActivateUi` with `state(key) → 'idle' | 'confirm' | 'busy'`, `click(key)`, 6 s confirm window; `PILL` styles copied verbatim from `logic.js` tones (`ok`, `warn`, `bad`, `info`, `mute`).

- [ ] **Step 1: Failing tests**

```ts
// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest';
import { toDataRows, useActivate } from './dataSources';

const rows = [
  { dataset_key: 'map_engine_leaflet', display_name: 'Map engine — Leaflet + Esri tiles', kind: 'engine', engines: ['leaflet'], active: true, license_status: 'cleared', license_name: 'BSD-2-Clause', notes: 'Approved design.', refresh_cadence: 'static' },
  { dataset_key: 'map_engine_google', display_name: 'Map engine — Google Maps Platform', kind: 'engine', engines: ['google'], active: false, license_status: 'cleared', license_name: 'Google Maps Platform Terms', notes: 'Basemap and satellite.', refresh_cadence: 'live' },
  { dataset_key: 'google_places_live', display_name: 'Google Places — live competitor pins', kind: 'dataset', engines: ['google'], active: false, license_status: 'unresolved', license_name: 'Google Maps Platform Terms + SST §14', notes: '', refresh_cadence: 'live' },
];

describe('toDataRows', () => {
  it('renders engine rows with Active/Cleared pills, an Activate action only on the inactive cleared engine, and the renders-on sub-line', () => {
    const ui = useActivate(vi.fn(async () => {}));
    const out = toDataRows(rows as never, ui);
    expect(out[0][2]).toMatchObject({ hasPill: true, pill: 'Active' });
    expect(out[0][3].hasActions).toBe(false);
    expect(out[1][2]).toMatchObject({ pill: 'Cleared' });
    expect(out[1][3].actions[0].label).toBe('Activate');
    expect(out[2][1].sub).toContain('Google map only — Terms §3.2.3(e)');
    expect(out[0][1].sub).toContain('Renders on: Leaflet');
  });
});

describe('useActivate', () => {
  it('needs two clicks within 6 s and posts once', async () => {
    vi.useFakeTimers();
    const post = vi.fn(async () => {});
    const ui = useActivate(post);
    ui.click('map_engine_google'); expect(ui.state('map_engine_google')).toBe('confirm'); expect(post).not.toHaveBeenCalled();
    vi.advanceTimersByTime(6001); expect(ui.state('map_engine_google')).toBe('idle');
    ui.click('map_engine_google'); await ui.click('map_engine_google');
    expect(post).toHaveBeenCalledWith('map_engine_google'); expect(post).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });
});
```

- [ ] **Step 2: Run to verify failure** — `npx vitest run src/admin` → FAIL.

- [ ] **Step 3: Implement** — `toDataRows` maps each row to `[cell(display_name, cadenceLabel), cell(license_name, sub), cell(null, null, pill, tone), cell(null, null, null, null, actions)]` where `sub = notes + ' · ' + (engines.length === 2 ? 'Renders on: Leaflet · Google' : engines[0] === 'google' ? 'Google map only — Terms §3.2.3(e)' : 'Leaflet only')`; pill/tone: engine rows `active → ('Active','ok')`, `cleared → ('Cleared','info')`, `unresolved → ('Unresolved','warn')`, `blocked → ('Blocked','bad')`; actions: engine rows that are cleared and inactive get `[{ label: ui.state(key) === 'confirm' ? 'Confirm switch' : 'Activate', tone: 'primary', go: () => ui.click(key) }]`. `useActivate` keeps a `Map<string, 'idle'|'confirm'|'busy'>` and a timer per key (6,000 ms); the second click sets `busy`, awaits `post(key)`, then `idle`. `PILL` and the action button style strings are copied verbatim from `logic.js:adminVals` (`A` and `cell` tone tables). Wiring into the rendered table is SP2's "replace fixtures with API calls" step for the Data tab; until then the fixture rows render unchanged (pixel gate intact).

- [ ] **Step 4: Run to verify passing** — `npx vitest run src/admin` → pass.

- [ ] **Step 5: Commit** — `feat(admin): Data Sources rows for engines with two-click Activate (mapping + state machine)`.

---

### Task M7: E2E — `app-google` project, Google loader stub, no-mixing, preload, activation

**Files:**
- Create: `frontend/e2e/engines.spec.ts`, `frontend/e2e/stubs/google-maps.js` (built by `npm run build:stubs` from `src/map/testing/google-stub.ts` with esbuild, IIFE, global `__stub`)
- Modify: `frontend/tests/playwright.config.ts` (project `app-google`, a `backend` webServer, `fullyParallel: false`, `dependencies`), `frontend/tests/harness.ts` (`prepare()` routes the Google loader to the stub), `frontend/package.json` (`build:stubs`)

**Interfaces:**
- Consumes: FastAPI on `http://localhost:8010` started by Playwright (`poetry run uvicorn app.main:app --port 8010` with `DATABASE_URL`/`REDIS_URL` from the CI services or `docker-compose.dev.yml`, all migrations applied by `scripts/migrate.py`, `MARKET_DATA_PUBLIC=true`, `API_SECRET_KEY` from env, `GOOGLE_MAPS_BROWSER_KEY=stub`, `GOOGLE_MAPS_MAP_ID=practice-match-web`), the built `frontend/dist`.
- Produces: the e2e proofs listed in the spec §10.

- [ ] **Step 1: Write the spec and the `app-google` project — no Google stub yet**

```ts
import { expect, test, type Page } from '@playwright/test';
import { prepare } from '../tests/harness';

const API = 'http://localhost:8010';
const H = { Authorization: `Bearer ${process.env.API_SECRET_KEY}` };

async function activate(request: Page['request'], key: string) {
  await request.post(`${API}/api/admin/data-sources/${key}/license`, { headers: H, data: { status: 'cleared' } });
  const r = await request.post(`${API}/api/admin/data-sources/${key}/activate`, { headers: H, data: { reason: 'e2e' } });
  expect(r.ok()).toBeTruthy();
  await new Promise((res) => setTimeout(res, 15500));   // the shell snapshot TTL
}

function recorder(page: Page) {
  const urls: string[] = []; const starts = new Map<string, number>(); const ends = new Map<string, number>();
  page.on('request', (r) => { urls.push(r.url()); starts.set(r.url(), Date.now()); });
  page.on('response', (r) => ends.set(r.url(), Date.now()));
  return { urls, starts, ends };
}

test.describe.serial('map engines', () => {
  test('Leaflet active: shell preloads the Leaflet chunk, Google is never requested, CSP names Leaflet hosts only', async ({ page }) => {
    await prepare(page);
    const rec = recorder(page);
    // `?tab=market` is a legacy no-op after Browse V3 (spec D4): Browse Practices is one
    // screen and always shows market data. The URL is kept here because it is the shape old
    // links take, and it must keep resolving.
    const resp = await page.goto(`${API}/browse?tab=market`);
    const html = await resp!.text();
    expect(html).toMatch(/<link rel="modulepreload" href="\/_app\/engine-leaflet-[a-z0-9]+\.js">/);
    expect(html).not.toContain('engine-google');
    expect(resp!.headers()['content-security-policy']).not.toContain('maps.googleapis.com');
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page.locator('[data-map="leaflet"]')).toHaveCount(1);
    expect(rec.urls.some((u) => /engine-google|maps\.googleapis\.com|maps\.gstatic\.com/.test(u))).toBe(false);
    const chunk = rec.urls.find((u) => /engine-leaflet-/.test(u))!; const app = rec.urls.find((u) => /\/_app\/index-/.test(u))!;
    expect(rec.starts.get(chunk)!).toBeLessThanOrEqual(rec.ends.get(app)!);   // preload started before the app bundle finished (P8)
  });

  test('activating Google swaps the shell, blocks Esri tiles, enables Google layers; both maps never coexist', async ({ page, request }) => {
    await activate(request, 'map_engine_google');
    await prepare(page);   // routes https://maps.googleapis.com/maps/api/js** to the stub
    const rec = recorder(page);
    // `?tab=market` is a legacy no-op after Browse V3 (spec D4): Browse Practices is one
    // screen and always shows market data. The URL is kept here because it is the shape old
    // links take, and it must keep resolving.
    const resp = await page.goto(`${API}/browse?tab=market`);
    expect(await resp!.text()).toMatch(/engine-google-[a-z0-9]+\.js/);
    expect(resp!.headers()['content-security-policy']).toContain('https://maps.googleapis.com');
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page.locator('[data-map="google"]')).toHaveAttribute('data-map-id', 'practice-match-web');
    expect(await page.locator('[data-map]').count()).toBe(1);
    expect(rec.urls.some((u) => /engine-leaflet|arcgisonline\.com|cartocdn\.com/.test(u))).toBe(false);
    const layers = await (await request.get(`${API}/api/layers`)).json();
    const byKey = Object.fromEntries(layers.layers.map((l: { key: string }) => [l.key, l]));
    expect(layers.engine).toBe('google'); expect(byKey.competition_live_points.engines).toEqual(['google']);
    const sources = Object.fromEntries((await (await request.get(`${API}/api/admin/data-sources`, { headers: H })).json()).map((r: { dataset_key: string }) => [r.dataset_key, r]));
    expect(sources.esri_tiles.engines).toEqual(['leaflet']);   // not eligible under Google
  });

  test('activating Leaflet again restores the design engine', async ({ page, request }) => {
    await activate(request, 'map_engine_leaflet');
    await prepare(page);
    // `?tab=market` is a legacy no-op after Browse V3 (spec D4): Browse Practices is one
    // screen and always shows market data. The URL is kept here because it is the shape old
    // links take, and it must keep resolving.
    await page.goto(`${API}/browse?tab=market`);
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page.locator('[data-map="leaflet"]')).toHaveCount(1);
  });
});
```
`playwright.config.ts`: `fullyParallel: false`; add `webServer` entry for the backend (`command: 'cd .. && poetry run python scripts/migrate.py && poetry run uvicorn app.main:app --port 8010'`, `url: 'http://localhost:8010/api/healthz'`, `reuseExistingServer: !process.env.CI`); add project `{ name: 'app-google', testMatch: /engines\.spec\.ts/, use: { ...devices['Desktop Chrome'], viewport: VIEWPORT }, dependencies: ['app'] }`. The visual project (`app`) keeps its full run; `engines.spec.ts` runs after it and leaves the database on Leaflet.

- [ ] **Step 2: Run — RED**

Run: `npm run build && npx playwright test --project=app-google` → the Leaflet test passes (it characterises M2–M5); the two Google tests **FAIL**: `[data-map="google"]` never mounts because the harness aborts `maps.googleapis.com` and no stub answers. Watch the failure message name the missing element.

- [ ] **Step 3: Add the loader stub route and `build:stubs`**

`harness.ts` `prepare()` adds:
```ts
await page.route('https://maps.googleapis.com/maps/api/js**', async (route) => {
  const cb = new URL(route.request().url()).searchParams.get('callback') ?? '__pmMapsReady';
  const stub = await fs.readFile(new URL('../e2e/stubs/google-maps.js', import.meta.url), 'utf8');
  await route.fulfill({ contentType: 'application/javascript', body: `${stub}\nwindow.google = __stub.makeGoogleStub([]).g;\nwindow[${JSON.stringify(cb)}]();` });
});
```

`package.json`: `"build:stubs": "esbuild src/map/testing/google-stub.ts --bundle --format=iife --global-name=__stub --outfile=e2e/stubs/google-maps.js"`.

- [ ] **Step 4: Run — GREEN**

Run: `npm run build:stubs && npx playwright test --project=app-google` → 3 passed (the middle test takes ~16 s for the snapshot TTL). Then `npx playwright test` → the full visual gate is still green.

- [ ] **Step 5: Commit** — `test(e2e): engine no-mixing, preload timing, activation round-trip with the Google stub`.

---

### Task M8: Google runtime pieces — live pins and live count (from the Google plan)

Execute the Google plan's **Task G3** (live competitor pins) and **Task G4** (live count proxy) as written in `docs/superpowers/plans/2026-09-05-practice-match-google-maps-greenfield.md`, with these deltas and no others:

| Google plan text | This plan |
|---|---|
| `engine.marker(p.position, pinContent(p), 'competition')` (G3) | `engine.marker([p.position.lat, p.position.lng], { html: pinContent(p).outerHTML, size: [18, 18], anchor: [9, 9], tooltip: pinTip(p) }, 'competition')` — `pinContent` returns the `.vet-pin` element; `pinTip(p)` returns the tooltip text (name, rating, address, "Google Maps" + attributions) |
| `useCompetitionLive(engine, g, layer, on, hub, band, note)` (G3) | unchanged, plus a guard: it runs only when `engine.name === 'google' && enabledFor(layer, 'google')` |
| `is_cleared(conn, "google_places_aggregate")` gate in G4 | `gate.enabled(reg["google_places_aggregate"], reg)` — eligibility, not just clearance (the count is a Google-map layer) |
| G4 test `test_gate_closed_returns_null_count…` | also asserts `reason == "gate"` when `google_places_aggregate` is cleared but the active engine is Leaflet |
| `registry key google_maps_js` (G5) | **not created** — `map_engine_google` (Task M1) is the engine row; G5 and G8 are superseded |
| G6 stub/mask | the stub is `src/map/testing/google-stub.ts` (M5); the mask rule is Task M7/M9 |


**TDD:** follow G3 and G4 Steps 1–5 exactly — failing tests first with the delta table applied to the **test code** before any implementation. RED runs: `cd frontend && npx vitest run src/map/competition.test.ts` → **FAIL** (`Cannot find module './competition'`); `poetry run pytest tests/api/test_competition_live.py -q` → **FAIL** (`ImportError: app.api.competition_live`). GREEN runs: the same commands → all pass; `poetry run pytest -q && npx vitest run` → everything else still green.

Commit messages as in the Google plan.

---

### Task M9: Docs, runbook, healthz, and cross-plan deltas

**Files:**
- Create: `docs/RUNBOOK-map-engines.md`
- Modify: `DEPLOY.md`, `app/api/health.py` (`map: {"engine": …}`), `tests/test_health.py`, `docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md` (API contract `/api/layers` shape; note on `esri_tiles`/`LEAFLET` constant follow-up), `docs/superpowers/plans/2026-09-05-practice-match-google-maps-greenfield.md` (status banner: G5/G8 superseded, engine row renamed)

- [ ] **Step 1: Failing tests**

`tests/test_health.py` — add:
```python
async def test_healthz_reports_the_active_map_engine_and_never_a_google_key(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "google_maps_browser_key", "browser-k")
    monkeypatch.setattr(settings, "google_maps_server_key", "server-k")
    r = await client.get("/api/healthz")
    assert r.json()["map"]["engine"] in {"leaflet", "google"}
    assert "browser-k" not in r.text and "server-k" not in r.text
```
`tests/test_docs.py` — add:
```python
def test_deploy_md_documents_the_map_engine_variables():
    text = (ROOT / "DEPLOY.md").read_text()
    for var in ("GOOGLE_MAPS_BROWSER_KEY", "GOOGLE_MAPS_MAP_ID", "GOOGLE_MAPS_SERVER_KEY", "ADMIN_ACTIVATE_ENABLED", "MARKET_DATA_PUBLIC"):
        assert var in text, var


def test_runbook_endpoints_exist():
    from app.main import app
    templates = {getattr(r, "path", "") for r in app.routes}
    runbook = (ROOT / "docs" / "RUNBOOK-map-engines.md").read_text()
    for path in set(re.findall(r"`(?:GET|POST) (/api/[^`\s]+)`", runbook)):
        norm = re.sub(r"/[a-z_]+_[a-z_]+(?=/|$)", "/{dataset_key}", path)   # `…/map_engine_google/activate` → the route template
        assert path in templates or norm in templates, path


def test_cross_plan_deltas_are_applied():
    census = (ROOT / "docs/superpowers/plans/2026-09-05-practice-match-census-data-layer.md").read_text()
    google = (ROOT / "docs/superpowers/plans/2026-09-05-practice-match-google-maps-greenfield.md").read_text()
    assert '"layers": [' in census and "Superseded in part by the Map-engines plan" in google
```
Run: `poetry run pytest tests/test_health.py tests/test_docs.py -q` → **FAIL** (`KeyError: 'map'`, `FileNotFoundError: docs/RUNBOOK-map-engines.md`, missing variables, missing delta text).

- [ ] **Step 2: Healthz, docs, deltas**

- Healthz: add `"map": {"engine": shell.snapshot().engine}` to the body.
- `DEPLOY.md`: the three Google variables (`GOOGLE_MAPS_BROWSER_KEY`, `GOOGLE_MAPS_MAP_ID` on `api`; `GOOGLE_MAPS_SERVER_KEY` on `api` for the count proxy), `ADMIN_ACTIVATE_ENABLED` (production: unset/false until SP2), `MARKET_DATA_PUBLIC=true` on QA only for evaluation.
- `docs/RUNBOOK-map-engines.md`: how to activate an engine (`POST /api/admin/data-sources/map_engine_google/activate` with the operator token; what changes within 15 s; `curl -sI / | grep -i content-security-policy` to verify), how to revert, how to read `GET /api/admin/data-sources/changes`, what a tripped Google quota looks like and what to do, key rotation.
- Census plan: API contract `/api/layers` → `{ "engine": …, "gate": …, "layers": [ … ] }`; B5 test snippets read `r.json()["layers"]`; Task B6 note: `map_config.LEAFLET` follows the cleared basemap row (`esri_tiles` or `osm_tiles`) when SP2 wires the Data tab.
- Google plan: status banner under the title — "Superseded in part by the Map-engines plan (2026-09-05): G2's engine is implemented as `frontend/src/map/engines/google.ts` behind `MapEngine`; G5 (`009_google_registry.sql`, `google_maps_js`, the tile-blocking trigger) and G8 (Leaflet removal) are replaced by registry row `map_engine_google` and the eligibility matrix; G1, G3, G4, G6-stub, G7 stand and are executed from Map-engines Tasks M7/M8."

- [ ] **Step 3: Run — GREEN**

Run: `poetry run pytest tests/test_health.py tests/test_docs.py -q` → all pass.

- [ ] **Step 4: Commit** — `docs(map-engines): runbook, deploy variables, healthz map.engine; cross-plan deltas`.

---

## Red-team review (2026-09-05) — findings and dispositions

| # | Finding | Severity | Disposition |
|---|---|---|---|
| E1 | The registry unique index alone cannot express "activate X and deactivate Y" in one statement. | Medium | Two statements in one transaction with `FOR UPDATE` on both rows (M4); the index is the backstop (M1 test). |
| E2 | `shell.snapshot()` reads Postgres; if it ran per request the shell would regress. | Medium | 15 s TTL, never raises, keeps the last snapshot (M2 tests count `_load_snapshot` calls). |
| E3 | An `X-PM-Gate` value computed from the snapshot can lag a decision by up to 15 s. | Low | Accepted — inside the spec's 60 s gate; e2e waits 15.5 s. |
| E4 | The e2e activation tests mutate shared state and run in parallel with the visual project. | Medium | `fullyParallel: false`, `dependencies: ['app']`, serial describe, final test restores Leaflet (M7). |
| E5 | `require_csrf` before `require_operator` means an unauthenticated cookie request sees 403 CSRF, not 401. | Info | Intended: CSRF failures never reveal whether a session is valid. |
| E6 | AdvancedMarker anchors content bottom-centre; Leaflet anchors by `iconAnchor`. | Medium | The Google engine's wrapper `transform` reproduces the anchor (M5 test asserts `translate(0px, 10px)` for a centred 20 px dot). |
| E7 | Fixture rows in the Admin tab stay until SP2 wires the API; the pixel gate would break if the engine rows were injected into fixtures. | Low | M6 delivers the mapping only; SP2 flips the tab to live rows. |
| E8 | The Google plan's G5 trigger would have blocked `osm_tiles` permanently. | Medium | Dropped; eligibility (`engines`) handles it without mutating licence status (M1). |

## Self-review

- **Spec coverage:** §2.1–2.2 (interface, two engines) → Platform Task 1b + M5; §2.3–2.4 (server-selected split bundles, preload) → M2 + M5 `manualChunks`; §2.5 (long-lived instance, debounce, no client swap, switch on route change, default Leaflet) → M5 host/gate + M8 debounce + M1 seed; §3 (DDL, rows, rule, activation) → M1 + M4; §4.1 (shell) → M2; §4.2 (CSP union, basemap validation) → M2 (`build_csp`, `validate_basemap_host` + allowlist test); §4.3 (endpoints) → M3 + M4 + M2 header; §5 (Admin rows) → M6; §6–§8 (S1–S15, P1–P11) → M2 (S1–S3, P1), M4 (S4–S6), M5 (S7, S10, P6), M8 (S8, S12–S13 via Google plan), M7 (S14, P7–P8), M9 (S15); §9 → M2 fallback + M5 host; §10 → tests in every task; §11 sequencing → header prerequisites; §12 → Google plan G1 + Platform §9; §13 DoD → M7 + M9 runbook checks.
- **Placeholders:** none; M8 references the Google plan's tasks by file and task id with an explicit delta table, because that code is complete there and duplicating ~300 lines would drift.
- **Type consistency:** `MountOptions`, `MarkerOptions`, `CircleStyle`, `LatLng = [lat, lng]`, `BaseKind = 'map' | 'satellite'` are defined in Platform Task 1b and used unchanged in M5's engine, host and tests; `gate.enabled(row, reg)` / `active_engine_name(reg)` (M1) are the only rule used by M2, M3, M8; `shell.snapshot()` is the only source of `engine`/`gate` for M2, M3, M9; `/api/layers` shape `{engine, gate, layers}` is identical in M3, M7 and the Census-plan delta (M9); `X-PM-Gate` is read by `apiFetch` (M5) and asserted in M2/M4.
