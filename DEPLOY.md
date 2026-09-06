# Practice Match deploy runbook

Railway project **Practice Match** (id `d20ecd90-2855-4b7d-957d-96a882b3a95d`) · environments `QA`, `production` · services `api`, `worker`, PostGIS database, `Redis`. One Docker image; `scripts/start.sh` picks the role from `RAILWAY_SERVICE_NAME`. `railway.json`: pre-deploy `python scripts/migrate.py`; the api container also runs the migrations at start (`scripts/start.sh`), which is the run that is actually observable in `railway logs`, healthcheck `/api/healthz`. PostGIS is pinned to `postgis/postgis:16-3.5` — the rolling `postgis/postgis:16-master` tag Railway's template ships must never be left in place. Two ways to set it, either fine, both **only after the 🚦 check below**: the dashboard (`Settings → Source → Image` on the `PostGIS` service, then **Deploy**), or the CLI — `railway service source connect --image postgis/postgis:16-3.5 --service PostGIS --environment <env>`.

## Variables (per service, per environment — set out-of-band, never in git or chat)

| Variable | api | worker | Value |
|---|---|---|---|
| `ENVIRONMENT` | ✓ | ✓ | `qa` / `production` (also builds `VITE_ENVIRONMENT`: jump bar on in QA, off in production) |
| `API_SECRET_KEY` | ✓ | ✓ | `openssl rand -hex 32`, different per environment |
| `ALLOWED_ORIGINS` | ✓ | ✓ | `https://qa.foundation.vin` / `https://foundation.vin` |
| `DATABASE_URL` | ✓ | ✓ | `${{PostGIS.DATABASE_PRIVATE_URL}}` (the `.railway.internal` private-network host, not the public proxy `DATABASE_URL` the template also exposes) |
| `REDIS_URL` | ✓ | ✓ | `${{Redis.REDIS_URL}}` |
| `COMMIT_SHA` | ✓ | ✓ | set by `scripts/deploy.sh` from `git rev-parse --short HEAD` immediately before each `railway up`; never set by hand |
| `PUBLIC_INDEXING` | ✓ | | `true` on production (the Coming Soon page is meant to be found); unset on QA → every response carries `X-Robots-Tag: noindex, nofollow` |
| `SITE_MODE` | ✓ | ✓ | `app` on QA, `coming_soon` on production until launch — selects the built site the api serves |
| `HIBP_ENABLED` | ✓ | | `true` in every environment; Have I Been Pwned k-anonymity password screen — falls back to the bundled offline list on any error (never disabled to skip the offline fallback, only to skip the network call in constrained environments) |
| `MARKET_DATA_PUBLIC` | ✓ | | `false` — anonymous visitors gain `market.read` only while `true`; QA evaluation only, **never** production (Identity plan Task I3) |
| `CONSOLIDATOR_KEYWORDS` | ✓ | | comma-separated employer-domain keywords, VIN Foundation-supplied; an application-review hint only, never a decision — default empty |
| `LINK_BASE_URL` | ✓ | ✓ | `https://qa.foundation.vin` / `https://foundation.vin` — the origin the verify and password-reset links in transactional email point at; a wrong value sends people to the other environment (Identity plan Task I4) |
| `EMAIL_ALLOWLIST` | ✓ | ✓ | comma-separated **whole addresses** (not domains) transactional email may be delivered to on any non-production environment. Fail-closed: outside production an **empty** list delivers to **nobody** — every row is recorded `suppressed` — so QA test sign-ups cannot email real people. Ignored on production, which delivers to everyone (Identity plan Task I6) |
| `DB_POOL_MAX` | ✓ | ✓ | `10` — the size of the psycopg2 **reuse pool** per DSN (`app/db.py`), which is what removes the per-request connect. It does **not** cap how many connections exist: past the pool a caller gets an un-pooled connection rather than an error, so the ceiling on backends is request concurrency, not this number. Bounding that overflow is Sub-project 2's concurrency work (Identity plan Task I9); raise this only if the pool is measured to be the bottleneck (Identity plan Task I4) |
| `MAIL_FROM` | | ✓ | `VIN Foundation — Practice Match <no-reply@foundation.vin>` — the Resend sender. `foundation.vin` is the sender domain only (spec §2); changing it needs the matching Resend DNS records (Identity plan Task I6) |
| `MAIL_REPLY_TO` | | ✓ | `practicematch@vin.com` — **placeholder**. The mailbox replies to transactional email reach is an open item for the VIN Foundation (spec §10); set the real one before launch (Identity plan Task I6) |
| `RESEND_API_KEY` | | ✓ | **worker only** — the Resend API key. John holds it; never in git, chat, or CI, same rule as `CENSUS_API_KEY`. `railway variable set RESEND_API_KEY=… --service worker --environment <env>`. A worker without it raises on every `mail.send` beat rather than leaving mail silently queued (Identity plan Task I6) |
| `RESEND_WEBHOOK_SECRET` | ✓ | | **api only** — the `whsec_…` signing secret Resend shows when the endpoint `https://<host>/api/webhooks/resend` is created. Same handling rule. Unset, the route answers `401` to every call rather than trusting one (Identity plan Task I6) |
| `CENSUS_API_KEY` | | ✓ | Sub-project 3; John holds it — never in git, chat, or CI. `railway variable set CENSUS_API_KEY=… --service worker --environment <env>` |
| `PERSONA_PASSWORD` | | | **Not a service variable.** Read from the shell by `scripts/seed_persona.py` only, and only outside production: `PERSONA_PASSWORD=… ENVIRONMENT=qa poetry run python scripts/seed_persona.py`. Unset it and the script uses its documented default (`.env.example`). Never set it in Railway — nothing in the api or worker reads it (Identity plan Task I5) |

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

Expected `verify-deploy.sh` output on QA (app mode, unchanged): `healthz OK  version X.Y.Z  commit <sha>  postgis 3.5.x`, `deep healthz OK`, `SPA fallback OK`. On production in coming-soon mode the script is site-mode aware: it reads `site_mode` from `/api/healthz` and swaps the SPA check for the coming-soon shell and the launch-notification endpoint — `healthz OK  version X.Y.Z  commit <sha>  postgis 3.5.x  site_mode coming_soon`, `deep healthz OK`, `coming-soon shell OK`, `interest endpoint OK` (no `SPA fallback OK` line in this mode). Boot lines to look for in `railway logs --service api --environment <env> --lines 50`: `[start.sh] role=api`, `Uvicorn running on http://0.0.0.0:<port>`; on the worker: `[start.sh] role=worker`, `celery@… ready`, `[worker-health] listening`.

**Nightly load smoke baseline** (`.github/workflows/perf.yml`, first manual run from `main`, 2026-09-06, 20 virtual users × 2 min against `https://qa.foundation.vin/api/healthz` — the only endpoint until Sub-project 2): p95 = 174 ms (budget 400 ms), median 118 ms, 22 054 requests, 0 % errors. Compare later runs against this line.

**`SKIP_VERIFY=1 scripts/deploy.sh <env>`** skips the automatic `verify-deploy.sh` call at the end of `deploy.sh`. It exists only to sequence the very first deploy of a brand-new commit (e.g. deploying `api` and `worker` back to back without the first one's probe racing the second's rollout) and must never be habitual — Railway's own healthcheck passes on an always-200 `/api/healthz` regardless of the database or Redis being reachable (Task 8 proved this: the first QA attempt was green in Railway with the database unreachable), so `scripts/verify-deploy.sh` is the only gate that actually reads component state (`db.ok`, `postgis_version`, the `/deep` endpoint's 200). Always let it run; only skip it deliberately, and always run it by hand immediately after if you do.

**`EXPECT_SHA`** is the commit `scripts/verify-deploy.sh` requires the live `/api/healthz` to report, so a stale container that answers 200 with yesterday's code fails the deploy: unset or empty both fall back to this checkout's `git rev-parse --short HEAD` (the script's `${EXPECT_SHA:-…}` cannot tell an empty value from an absent one), a non-empty value is compared verbatim, and the assertion is skipped only when the script runs outside a git checkout, where `git rev-parse` yields nothing to compare against. When the branch has moved past the tree that is actually deployed, pass the deployed commit explicitly — `EXPECT_SHA=087acc1 scripts/verify-deploy.sh QA` — because the default would otherwise demand a HEAD that was never shipped.

## Automation tokens

An `api_token` is how CI and the load smoke authenticate (`k6-qa`, `e2e-qa`, `deploy-verify`); it replaces `API_SECRET_KEY`, which goes away with `auth_stub.py` once those secrets are switched over.

* **Minting** — an admin, with a password confirmation in the last 10 minutes: `POST /api/admin/tokens {"name": "e2e-qa", "role": "staff", "days": 90}`. The role may be any of `buyer`, `seller`, `staff` or `admin` (John's ruling, 2026-09-07); nobody may mint a token that administers more than they do. The mint is audited (`tokens.create`, with the role).
* **The value is shown once** — the response is `{"token": "pm_<id>.<secret>"}` and only its SHA-256 is stored, so a token that is not copied out of that response is gone. Present it as `Authorization: Bearer pm_<id>.<secret>`; it needs no cookie and no CSRF header. Put it in the CI secret store, never in git or chat.
* **Two things a token can never do**, whatever role it carries: it can never **re-authenticate** (Revoke, licence decisions, engine activation, role grants and token creation answer `403 REAUTH_TOKEN`), and it can never **manage tokens** (`403 TOKEN_SCOPE`). A leaked admin token cannot revoke a member or mint its own successor.
* **Lifetime** — capped at 90 days (`days` is clamped into 1..90) and tied to its minter: suspending or revoking that account kills every token it minted, on the next request.
* **Revoking** — `POST /api/admin/tokens/{id}/revoke` (audited, `404` if it is already revoked). Rotate by minting the replacement first, switching the CI secret, then revoking the old one.
* **Demotion revokes automatically** — removing someone's `staff` or `admin` grant (`POST /api/admin/users/{id}/grants` with `"grant": false`) revokes, in the same transaction, every live token they minted whose role they may no longer mint; a `buyer`/`seller` automation token is left alone. The ids come back in the response as `revoked_tokens`, and the trail carries one row per token: `GET /api/admin/audit` → `action='tokens.revoke'`, `reason='grant_removed'`, `after.role` = the token's role. There is no list-tokens endpoint, so that response and the audit trail are the record — check them when you demote someone, and mint replacements from an account that still holds the role.

## Site mode (Coming Soon on production)

| Variable | QA | production |
|---|---|---|
| `ENVIRONMENT` | `qa` | `production` |
| `SITE_MODE` | `app` | `coming_soon` |
| `PUBLIC_INDEXING` | unset (noindex) | `true` |

Production publishes the VIN Foundation Coming Soon page (`coming-soon/`); QA is the marketplace. The coming-soon page never goes to QA — `scripts/verify-deploy.sh` now asserts `site_mode` per environment and refuses a mismatch outright: QA takes no override and fails any `coming_soon` body; production expects `coming_soon` by default, overridable with `EXPECT_SITE_MODE`. **Launch:** `railway status` (Project: Practice Match) → `railway variable set SITE_MODE=app --service api --environment production --skip-deploys` (and `--service worker`) → decide `PUBLIC_INDEXING` → `EXPECT_SITE_MODE=app scripts/deploy.sh production` (the prefix reaches the verifier `deploy.sh` runs; without it the deploy's own verification refuses `app` on production) → change the verifier's production default to `app` in the same release.

**Client address for the sign-up rate limits.** `/api/interest` keys its per-IP limits on the **first X-Forwarded-For hop**, exactly as uvicorn does under `--forwarded-allow-ips='*'`: Railway's edge writes the client it accepted first and leaves any caller-supplied values after it (verified 2026-09-06 on QA — uvicorn logged the real client for spoofed headers, and the probe below limited the sixth request with one header line and with two). A first hop that is not a valid IP address (`ipaddress.ip_address` refuses it) is not trusted as an address at all: it is bucketed as the single subject `unknown`, so a caller reaching the api off the edge cannot mint a fresh rate-limit bucket per forged header. The header is trusted from any peer, as that uvicorn flag already implies; only Railway's edge and the project's private network reach the api. Re-run both passes against QA whenever Railway's networking changes. Each pass writes up to 5 rows into QA's `interest_signup` and spends 6 of the operator IP's 30/day budget, so at most five passes a day; expected `202 202 202 202 202 429` from each pass — **anything other than `202 ×5` then `429` (a sixth `202`, any `503`, a `429` before the sixth) means stop and investigate before any production deploy.**
```bash
T=$(date +%s)
for i in 1 2 3 4 5 6; do curl -sS -o /dev/null -w "%{http_code} " -X POST -H 'Content-Type: application/json' -H "X-Forwarded-For: 203.0.113.$i" -d "{\"email\":\"probe-$T-a$i@example.invalid\"}" https://qa.foundation.vin/api/interest; done; echo; sleep 61
for i in 1 2 3 4 5 6; do curl -sS -o /dev/null -w "%{http_code} " -X POST -H 'Content-Type: application/json' -H "X-Forwarded-For: 198.51.100.$i" -H "X-Forwarded-For: 198.51.100.99" -d "{\"email\":\"probe-$T-b$i@example.invalid\"}" https://qa.foundation.vin/api/interest; done; echo
```

## Rollback

Redeploy the previous image/deployment for the service — Railway dashboard → the service → **Deployments** → pick the last good one → **Redeploy** — then re-run `scripts/verify-deploy.sh <env>` to confirm.

| Failure | Action | RTO |
|---|---|---|
| Bad build on QA | fix forward; QA is disposable | — |
| Regression on production | redeploy the previous deployment (dashboard → service → Deployments → Redeploy); `scripts/verify-deploy.sh production` | ~5 min |
| Migration failed (a SQL file errors) | The api container runs the migrations at start and exits before uvicorn (`[start.sh] migration failed`), so the new container never serves; the failed file was not recorded. Fix the SQL and redeploy. Whether Railway keeps the previous deployment serving meanwhile depends on its health-gated rollout, which the deployment manifest has not shown honouring railway.json — check the dashboard, and if the old deployment is gone, redeploy the last good one (row above). | — |
| Database unreachable at boot | The api retries the migrations (`MIGRATE_RETRIES`×`MIGRATE_RETRY_SLEEP`, default 5 × 5 s), then serves anyway so the static site stays up; sign-ups answer 503 until the database returns and a restart applies the files (`railway restart --service api`). | — |
| Worker crash-loop | `railway logs --service worker --environment <env> --lines 50`; the health server exits with Celery so Railway restarts it — check `REDIS_URL` reference and Redis service health | — |
| Wrong project deployed | `scripts/deploy.sh` refuses; if a bare `railway up` was used, redeploy the affected project's own last good commit | — |

## The home-directory hazard (fixed 2026-09-06 — the rule still stands)

The Railway CLI resolves the linked project by walking **up** the directory tree. `~/.railway/config.json` had linked `/Users/johndean` itself to another project (CE.VIN), so every unlinked folder anywhere under `$HOME` inherited CE.VIN's production — an unguarded `railway up` from a fresh, unlinked checkout would have deployed this app over CE.VIN's live `api`. The home-directory link was removed on 2026-09-06, but a future clone or a different machine can reintroduce the same trap. The rule is unconditional: run `railway status` and read the `Project:` line before any `railway up`, variable, service, or domain change; never pass `--project` from memory; never set a global `RAILWAY_TOKEN`.
