# Practice Match

VIN Foundation veterinary practice marketplace. Production https://foundation.vin · QA https://qa.foundation.vin.

- **Design (SSOT):** `docs/design-reference/design_handoff_practice_match_v2/Practice Match V2.dc.html` — every pixel in `frontend/` must match it; `npm run test:visual` proves it.
- **Frontend:** Vue 3 + Vite in `frontend/` (the approved handoff, plus a router sync layer). `npm run typecheck && npm test && npm run build`.
- **Backend:** FastAPI + Celery in `app/`, SQL migrations in `migrations/`, one Docker image, Railway services `api` + `worker` + PostGIS + Redis.
- **Tests:** `docker compose -f docker-compose.dev.yml up -d && poetry run pytest` · `cd frontend && npm run test:smoke && npm run test:visual:baselines && npm run test:visual`.
- **Deploy:** `scripts/deploy.sh QA` → verify on qa.foundation.vin → `scripts/deploy.sh production`. Read `CLAUDE.md` and `DEPLOY.md` first.
- **Specs and plans:** `docs/superpowers/specs/`, `docs/superpowers/plans/`.
