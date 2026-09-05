# Practice Match deploy runbook

Railway project **Practice Match** (id `d20ecd90-2855-4b7d-957d-96a882b3a95d`) · environments `QA`, `production` · services `api`, `worker`, PostGIS database, `Redis`. One Docker image; `scripts/start.sh` picks the role from `RAILWAY_SERVICE_NAME`. `railway.json`: pre-deploy `python scripts/migrate.py`, healthcheck `/api/healthz`. PostGIS is pinned to `postgis/postgis:16-3.5` — the rolling `postgis/postgis:16-master` tag Railway's template ships must never be left in place. Two ways to set it, either fine, both **only after the 🚦 check below**: the dashboard (`Settings → Source → Image` on the `PostGIS` service, then **Deploy**), or the CLI — `railway service source connect --image postgis/postgis:16-3.5 --service PostGIS --environment <env>`.

## Variables (per service, per environment — set out-of-band, never in git or chat)

| Variable | api | worker | Value |
|---|---|---|---|
| `ENVIRONMENT` | ✓ | ✓ | `qa` / `production` (also builds `VITE_ENVIRONMENT`: jump bar on in QA, off in production) |
| `API_SECRET_KEY` | ✓ | ✓ | `openssl rand -hex 32`, different per environment |
| `ALLOWED_ORIGINS` | ✓ | ✓ | `https://qa.foundation.vin` / `https://foundation.vin` |
| `DATABASE_URL` | ✓ | ✓ | `${{PostGIS.DATABASE_PRIVATE_URL}}` (the `.railway.internal` private-network host, not the public proxy `DATABASE_URL` the template also exposes) |
| `REDIS_URL` | ✓ | ✓ | `${{Redis.REDIS_URL}}` |
| `COMMIT_SHA` | ✓ | ✓ | set by `scripts/deploy.sh` from `git rev-parse --short HEAD` immediately before each `railway up`; never set by hand |
| `PUBLIC_INDEXING` | ✓ | | `false` until launch (default) — every response carries `X-Robots-Tag: noindex, nofollow` until flipped to `true` |
| `CENSUS_API_KEY` | | ✓ | Sub-project 3; John holds it — never in git, chat, or CI. `railway variable set CENSUS_API_KEY=… --service worker --environment <env>` |

## DNS (verbatim as Railway printed them — Task 8, 2026-09-06)

Both custom domains need **all four** records below, not just a CNAME each — Railway shows `Verified: no` / `CERTIFICATE_STATUS_TYPE_VALIDATING_OWNERSHIP` until the TXT ownership record also resolves. DNS changes can take up to 72 hours to propagate worldwide.

| Host | Type | Name | Value |
|---|---|---|---|
| `qa.foundation.vin` | CNAME | `qa` | `va7f7sbq.up.railway.app` |
| `qa.foundation.vin` | TXT | `_railway-verify.qa` | `railway-verify=7b12d7490dc75edd5a53905f248d52e61b37f924b8b680eb389966e22c11d9c4` |
| `foundation.vin` | CNAME | `@` (apex) | `iz4g9ph8.up.railway.app` |
| `foundation.vin` | TXT | `_railway-verify` | `railway-verify=dd94ec458f0f18d4ca0806f5e1803bc5371ba016976b18601e795ba3bedb5292` |

`foundation.vin`'s record is an **apex CNAME**, not the A record the plan originally expected — the DNS provider must support ALIAS / ANAME / CNAME-flattening at the root; a plain CNAME at the apex is invalid on providers without it. Check propagation with `dig +short qa.foundation.vin CNAME`, `dig +short foundation.vin CNAME`, `dig +short _railway-verify.qa.foundation.vin TXT`, `dig +short _railway-verify.foundation.vin TXT`, then `railway domain status a066b6b3-bca4-4cd8-bbfb-ae21d2a24531` (QA) / `railway domain status d9e291e7-498c-40a7-9fe3-f8b54c695986` (production). Until DNS is live, verify against the Railway-issued hosts directly: QA `https://api-qa-f3b3.up.railway.app`, production `https://api-production-ebcf.up.railway.app` (pass as `scripts/verify-deploy.sh ENV <url>` or set `VERIFY_BASE_URL`).

## Deploy

```bash
railway status                       # MUST print Project: Practice Match
scripts/deploy.sh QA                 # api + worker → verify-deploy.sh QA
# click through the changed flow on https://qa.foundation.vin
scripts/deploy.sh production         # api + worker → verify-deploy.sh production
```

Expected `verify-deploy.sh` output: `healthz OK  version X.Y.Z  commit <sha>  postgis 3.5.x`, `deep healthz OK`, `SPA fallback OK`. Boot lines to look for in `railway logs --service api --environment <env> --lines 50`: `[start.sh] role=api`, `Uvicorn running on http://0.0.0.0:<port>`; on the worker: `[start.sh] role=worker`, `celery@… ready`, `[worker-health] listening`.

**`SKIP_VERIFY=1 scripts/deploy.sh <env>`** skips the automatic `verify-deploy.sh` call at the end of `deploy.sh`. It exists only to sequence the very first deploy of a brand-new commit (e.g. deploying `api` and `worker` back to back without the first one's probe racing the second's rollout) and must never be habitual — Railway's own healthcheck passes on an always-200 `/api/healthz` regardless of the database or Redis being reachable (Task 8 proved this: the first QA attempt was green in Railway with the database unreachable), so `scripts/verify-deploy.sh` is the only gate that actually reads component state (`db.ok`, `postgis_version`, the `/deep` endpoint's 200). Always let it run; only skip it deliberately, and always run it by hand immediately after if you do.

## Rollback

Redeploy the previous image/deployment for the service — Railway dashboard → the service → **Deployments** → pick the last good one → **Redeploy** — then re-run `scripts/verify-deploy.sh <env>` to confirm.

| Failure | Action | RTO |
|---|---|---|
| Bad build on QA | fix forward; QA is disposable | — |
| Regression on production | redeploy the previous deployment (dashboard → service → Deployments → Redeploy); `scripts/verify-deploy.sh production` | ~5 min |
| Migration failed | Deploy aborted by the pre-deploy hook; the running version stays. Fix the SQL file (it was not recorded) and redeploy | — |
| Worker crash-loop | `railway logs --service worker --environment <env> --lines 50`; the health server exits with Celery so Railway restarts it — check `REDIS_URL` reference and Redis service health | — |
| Wrong project deployed | `scripts/deploy.sh` refuses; if a bare `railway up` was used, redeploy the affected project's own last good commit | — |

## The home-directory hazard (fixed 2026-09-06 — the rule still stands)

The Railway CLI resolves the linked project by walking **up** the directory tree. `~/.railway/config.json` had linked `/Users/johndean` itself to another project (CE.VIN), so every unlinked folder anywhere under `$HOME` inherited CE.VIN's production — an unguarded `railway up` from a fresh, unlinked checkout would have deployed this app over CE.VIN's live `api`. The home-directory link was removed on 2026-09-06, but a future clone or a different machine can reintroduce the same trap. The rule is unconditional: run `railway status` and read the `Project:` line before any `railway up`, variable, service, or domain change; never pass `--project` from memory; never set a global `RAILWAY_TOKEN`.
