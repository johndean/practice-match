# CLAUDE.md — Practice Match

VIN Foundation veterinary practice marketplace (internal working title). Read this, then `.claude/skills/practice-match-workflow/SKILL.md` (the craft), before substantive work.

## Environments

| | URL | Railway env | Backend | Use |
|---|---|---|---|---|
| QA | https://qa.foundation.vin | `QA` | own PostGIS + Redis (isolated) | verify everything here first; test freely |
| Production | https://foundation.vin | `production` | own PostGIS + Redis | stakeholders' real data once Sub-project 2 ships |

`GET /api/healthz` on either host returns `environment`, `version`, `commit_sha`, `db.postgis_version`, `redis.ok`. **John does not run the app locally** — the loop is code → `scripts/deploy.sh QA` → verify on qa.foundation.vin → `scripts/deploy.sh production` → smoke on foundation.vin.

Every environment variable is set only in Railway (per service, per environment) — see `.env.example` for the full list and `DEPLOY.md` for how each is set. `CENSUS_API_KEY` (worker only, Sub-project 3; John holds it) is the one that must never appear in git, chat, or a CI log — same rule as `API_SECRET_KEY`, just worth naming.

> ### 🚦 ALWAYS confirm the Railway target before uploading or changing anything
> This machine runs 5+ Railway projects; `railway up` ships to whatever is linked. Before ANY `railway up`, variable change, or service mutation run `railway status` and read it back — it must say **Project: Practice Match**. `scripts/deploy.sh` enforces this; do not bypass it with a bare `railway up`. Never pass `--project` from memory. Never set a global `RAILWAY_TOKEN`.

## Source of truth for the UI

`docs/design-reference/design_handoff_practice_match_v2/Practice Match V2.dc.html` is the approved design. Rules, each violated by an assistant somewhere before:

- **Reference open first, port verbatim, absent beats faked.** No invented UI, no placeholder banners, no "TODO Phase X", no simplifications.
- **Ported files are byte-identical** except the edits listed in `docs/superpowers/specs/2026-09-05-practice-match-platform-design.md` §3. `logic.js` is never restructured. Inline styles stay inline. No CSS framework, no Pinia, no per-screen split without a visual diff per screen.
- **`npm run test:visual` is the arbiter.** Baselines are generated from the reference in the same run (`npm run test:visual:baselines`). Tolerance is zero (`playwright.config.ts`); relaxing it requires a recorded reason.
- The design-system cascade matters: `frontend/index.html` links `colors_and_type.css`, `preview/_preview.css`, `ui_kits/vin/kit.css` in that order, before the app styles.

## Non-negotiables (from po.vin / rounds.vin, still true here)

- **Surgical diffs.** The change contains the ask and nothing else. Never remove a function or feature while doing unrelated work. No drive-by refactors or reformatting.
- **No destructive actions** without explicit instruction in the current conversation.
- **Verification gate before every production deploy — all four:** (1) `poetry run pytest` + `npm run typecheck && npm test && npm run build`; (2) `npm run test:smoke` and `npm run test:visual` green; (3) click-through on https://qa.foundation.vin of the changed flow; (4) post-deploy smoke on https://foundation.vin (`scripts/verify-deploy.sh production`). Verified = ship; no need to ask.
- **Push every commit to both remotes:** `origin` (vin-swe/practice-match) and `production` (johndean/practice-match). Conventional commits; trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- **Versions in lockstep:** `frontend/package.json` and `pyproject.toml`, one patch per release (`tests/test_versions.py`).
- **Close the loop:** forwardable plain-language summary + screenshots of the live screens + a one-line engineer's note with any risk.

## Legally load-bearing (from the approved design and the Census spec)

- **Attribution stays visible** on every map ("Tiles © Esri" today; whatever the VIN Foundation's final basemap licence requires) and under Community Context ("Source: U.S. Census Bureau, …"). Attribution strings will come from `dataset_registry.attribution_text`, not hard-coded, once Sub-project 3 lands.
- **Blocked datasets never ship.** Pet-ownership incidence (licence unresolved) and third-party practice-location data must not be ingested or displayed until the VIN Foundation clears them. The admin Data Sources tab shows this gate; keep it.
- **Open licence question:** the design uses Esri basemap tiles; the Census spec registered CARTO. Do not swap either way without the VIN Foundation's decision (spec §9).

## Launch-removal list (execute in Sub-project 2, with real auth)

Prototype jump bar markup (`prototypeBar`, already off in production) · "Prototype — access states" shortcuts on the sign-in card · pre-filled demo credentials · `startScreen`/`startViewport` props · fixture data in `logic.js` (`P`, `MARKETS`, `VETS`, `ECON_K`, `sellerListings`, `requests`, admin rows — keep field names; the UI reads them).

## Layout

`frontend/` Vue app · `frontend/tests/` Playwright (`screens.ts` = the 25 approved states) · `app/` FastAPI (`api/health.py`, `static.py`, `checks.py`, `tasks/celery_app.py`) · `migrations/` numbered SQL (ledger runner `scripts/migrate.py`) · `scripts/` `start.sh` (roles api|worker|migrate), `deploy.sh`, `verify-deploy.sh`, `verify-image.sh` · `tests/` pytest · `docs/design-reference/` the handoff bundle (never shipped) · `docs/superpowers/{specs,plans}/`.

## Common operations

```bash
docker compose -f docker-compose.dev.yml up -d && poetry run pytest            # backend tests
cd frontend && npm run typecheck && npm test && npm run build                  # frontend gates
cd frontend && npm run test:smoke && npm run test:visual:baselines && npm run test:visual
scripts/deploy.sh QA && scripts/deploy.sh production                           # after the gate
railway logs --service api --environment QA --lines 50
railway variable list --service api --environment QA | sed -E 's/(SECRET|KEY|URL)=.*/\1=<redacted>/'
```
