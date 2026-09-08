# Practice Match

VIN Foundation veterinary practice marketplace. Production https://foundation.vin · QA https://qa.foundation.vin.

- **Design (SSOT):** `docs/design-reference/design_handoff_practice_match_v2/Practice Match V2.dc.html` — every pixel in `frontend/` must match it; `npm run test:visual` proves it.
- **Frontend:** Vue 3 + Vite in `frontend/` (the approved handoff, plus a router sync layer). `npm run typecheck && npm test && npm run build`.
- **Backend:** FastAPI + Celery in `app/`, SQL migrations in `migrations/`, one Docker image, Railway services `api` + `worker` + PostGIS + Redis.
- **Tests:** `docker compose -f docker-compose.dev.yml up -d && poetry run pytest` · `docker compose -f docker-compose.dev.yml up -d && cd frontend && npm run test:visual:baselines && npm run test:e2e`. Every Playwright command needs the compose Postgres/Redis: the `app` project starts the real API against them (`frontend/tests/targets.ts`), so with Docker down the run dies after a 90 s wait for a server that never booted.
  - *Scratch databases (platform task P-TDB).* The backend suite migrates ONCE per session, into a template database called `pm_tmpl_<hex>`, and hands each database-backed test a `CREATE DATABASE … TEMPLATE` clone of it (`tests/conftest.py`'s `template_dsn` and `scratch_dsn`) rather than running the whole migration ladder into an empty database per test. The clone still runs the migrator, which on an already-migrated copy applies nothing and only re-verifies the ledger — so a migration file that changed after it was applied is still refused, per test. Postgres will not copy a database another session is connected to: if it answers `source database … is being accessed by other users`, the fixture warns once and falls back to the old create-then-migrate path for that one test, so a shared Postgres makes the run slower and never wrong. The template is dropped when the session ends.
- **Deploy:** `scripts/deploy.sh QA` → verify on qa.foundation.vin → `scripts/deploy.sh production`. Read `CLAUDE.md` and `DEPLOY.md` first.
- **Specs and plans:** `docs/superpowers/specs/`, `docs/superpowers/plans/`.
