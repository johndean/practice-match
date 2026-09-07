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
| `COMMIT_SHA` | ✓ | ✓ | set by `scripts/deploy.sh` from `git rev-parse --short HEAD` immediately before each `railway up`; never set by hand. A fallback only since P14: `/api/healthz` prefers the image's own `/app/BUILD_SHA` stamp, which travels inside the upload and so cannot be set independently of the deployed tree |
| `PUBLIC_INDEXING` | ✓ | | `true` on production (the Coming Soon page is meant to be found); unset on QA → every response carries `X-Robots-Tag: noindex, nofollow` |
| `SITE_MODE` | ✓ | ✓ | `app` on QA, `coming_soon` on production until launch — selects the built site the api serves |
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
railway status                             # MUST print Project: Practice Match
scripts/deploy.sh QA                       # api + worker → verify-deploy.sh QA
scripts/deploy.sh QA .worktrees/<branch>   # to deploy a branch: SOURCE_DIR is what gets archived
# click through the changed flow on https://qa.foundation.vin
scripts/deploy.sh production               # api + worker → verify-deploy.sh production
```

**What actually gets uploaded** (P14, 2026-09-07). `scripts/deploy.sh QA|production [SOURCE_DIR]` extracts `git archive HEAD` of SOURCE_DIR into a temp directory (removed on exit) and hands *that* to `railway up "$TMP" --path-as-root`, so the upload contains no `.git`, no untracked files and no uncommitted edits. SOURCE_DIR defaults to the script's own repo root; **to deploy a branch, pass it — `scripts/deploy.sh QA .worktrees/<branch>`** — never `cd` into a worktree and hope. The hazard this closes: run from the linked worktree `.worktrees/feat-browse-v3`, `railway up` (CLI 5.26.0) resolved the upload root through that worktree's `.git` **pointer file** back to the main repository directory and uploaded MAIN's tree; QA served main's `pyproject` 0.1.0 and main's `App.vue` strings while `/api/healthz` reported the branch's commit, because that sha was the `COMMIT_SHA` variable `deploy.sh` had just set. `--path-as-root` is load-bearing: without it the CLI filters the path against "the project directory" it resolves for itself, which is the same mis-resolution.

`scripts/deploy.sh` exit codes:

| Code | Meaning | What to do |
|---|---|---|
| `exit 64` | usage: the environment is not `QA`/`production`, or SOURCE_DIR is not a directory or not a git working tree | fix the arguments |
| `exit 65` | 🚦 the linked Railway project is not **Practice Match** | `railway link`, then `railway status` |
| `exit 66` | SOURCE_DIR has uncommitted changes to tracked files — the upload is HEAD, so those edits would silently not ship | commit them, or pass a SOURCE_DIR that is committed. Untracked files are fine and are simply left out |
| `exit 67` | the upload created no deployment, or the deployment did not reach `SUCCESS` | read the message: either the upload itself failed and **nothing was deployed**, or `railway logs --service <svc> --environment <env> --lines 100` |

The 67 path exists because `railway up --ci` streams build logs and that stream can time out (`reqwest error … operation timed out`) *after* the upload succeeded, while the deployment carries on — aborting there would leave the api deployed and the worker not. A non-zero `up` is therefore resolved by asking Railway what actually happened, and it **fails closed**: the newest deployment's `createdAt` is recorded *before* the upload, and a deployment with a **strictly newer** `createdAt` must appear within 120 s or the script exits 67 with `upload did not create a deployment for <service>`. That guard matters because `up` also exits non-zero when the upload itself failed, and then Railway's newest deployment is still the previous deploy's — very possibly a `SUCCESS`, which a status-only poll would misread as this deploy succeeding. A deployment whose JSON carries no `createdAt` cannot be dated and so reads as "no new deployment" (67) rather than being trusted or waited on for ever. Once identified, that deployment and only that one (by `id` where the CLI supplies one) is polled to `SUCCESS` — continue to the next service — or `FAILED`/`CRASHED` (67), within a 15-minute bound. `DEPLOY_POLL_INTERVAL` / `DEPLOY_APPEAR_TIMEOUT` / `DEPLOY_POLL_TIMEOUT` override the 10 s / 120 s / 900 s bounds; the shell tests set them to seconds.

Expected `verify-deploy.sh` output on QA (app mode, unchanged): `healthz OK  version X.Y.Z  commit <sha>  postgis 3.5.x`, `deep healthz OK`, `SPA fallback OK`. On production in coming-soon mode the script is site-mode aware: it reads `site_mode` from `/api/healthz` and swaps the SPA check for the coming-soon shell and the launch-notification endpoint — `healthz OK  version X.Y.Z  commit <sha>  postgis 3.5.x  site_mode coming_soon`, `deep healthz OK`, `coming-soon shell OK`, `interest endpoint OK` (no `SPA fallback OK` line in this mode). Boot lines to look for in `railway logs --service api --environment <env> --lines 50`: `[start.sh] role=api`, `Uvicorn running on http://0.0.0.0:<port>`; on the worker: `[start.sh] role=worker`, `celery@… ready`, `[worker-health] listening`.

**Nightly load smoke baseline** (`.github/workflows/perf.yml`, first manual run from `main`, 2026-09-06, 20 virtual users × 2 min against `https://qa.foundation.vin/api/healthz` — the only endpoint until Sub-project 2): p95 = 174 ms (budget 400 ms), median 118 ms, 22 054 requests, 0 % errors. Compare later runs against this line.

**`SKIP_VERIFY=1 scripts/deploy.sh <env>`** skips the automatic `verify-deploy.sh` call at the end of `deploy.sh`. It exists only to sequence the very first deploy of a brand-new commit (e.g. deploying `api` and `worker` back to back without the first one's probe racing the second's rollout) and must never be habitual — Railway's own healthcheck passes on an always-200 `/api/healthz` regardless of the database or Redis being reachable (Task 8 proved this: the first QA attempt was green in Railway with the database unreachable), so `scripts/verify-deploy.sh` is the only gate that actually reads component state (`db.ok`, `postgis_version`, the `/deep` endpoint's 200). Always let it run; only skip it deliberately, and always run it by hand immediately after if you do.

**`EXPECT_SHA`** is the commit `scripts/verify-deploy.sh` requires the live `/api/healthz` to report, so a stale container that answers 200 with yesterday's code fails the deploy: unset or empty both fall back to this checkout's `git rev-parse --short HEAD` (the script's `${EXPECT_SHA:-…}` cannot tell an empty value from an absent one), a non-empty value is compared verbatim, and the assertion is skipped only when the script runs outside a git checkout, where `git rev-parse` yields nothing to compare against. When the branch has moved past the tree that is actually deployed, pass the deployed commit explicitly — `EXPECT_SHA=087acc1 scripts/verify-deploy.sh QA` — because the default would otherwise demand a HEAD that was never shipped.

**`EXPECT_VERSION`** is the release version the live `/api/healthz` must report, and it is the probe that proves the deployed **artefact** rather than a variable. `commit_sha` could not: it was the `COMMIT_SHA` service variable `deploy.sh` sets immediately before each upload, so it agreed with the deploy even in P14, when the tree that had actually been uploaded was a different one. `version` is read from the `pyproject.toml` *inside the image*, so a tree that is not the one we built shows up here — a mismatch fails with one `FAIL:` line naming both versions. `deploy.sh` passes the version of the tree it archived; run by hand the default is the version in the `pyproject.toml` beside the script, and (as with `EXPECT_SHA`) unset and empty behave identically, the assertion being skipped only when that file is unreadable or carries no version. **After deploying a SOURCE_DIR other than this checkout**, both defaults are wrong for a hand-run verification — the verifier would demand this checkout's version and sha and report `FAIL: version is …, expected …` against a perfectly good deploy — so re-run it as `EXPECT_SHA=<sha> EXPECT_VERSION=<version> scripts/verify-deploy.sh QA`, with the sha and version of the tree that was archived. `scripts/deploy.sh` prints that exact line, filled in, after every successful deploy. `commit_sha` is now an artefact property too: it is the contents of `/app/BUILD_SHA`, a file `deploy.sh` writes into the archive and the Dockerfile copies, falling back to the `COMMIT_SHA` variable only when the image carries no stamp (a git-connected Railway build, or a local `docker build`).

## Site mode (Coming Soon on production)

| Variable | QA | production |
|---|---|---|
| `ENVIRONMENT` | `qa` | `production` |
| `SITE_MODE` | `app` | `coming_soon` |
| `PUBLIC_INDEXING` | unset (noindex) | `true` |

Production publishes the VIN Foundation Coming Soon page (`coming-soon/`); QA is the marketplace. The coming-soon page never goes to QA — `scripts/verify-deploy.sh` now asserts `site_mode` per environment and refuses a mismatch outright: QA takes no override and fails any `coming_soon` body; production expects `coming_soon` by default, overridable with `EXPECT_SITE_MODE`. **Launch:** `railway status` (Project: Practice Match) → `railway variable set SITE_MODE=app --service api --environment production --skip-deploys` (and `--service worker`) → decide `PUBLIC_INDEXING` → `EXPECT_SITE_MODE=app scripts/deploy.sh production` (the prefix reaches the verifier `deploy.sh` runs; without it the deploy's own verification refuses `app` on production) → change the verifier's production default to `app` in the same release.

**Client address for the sign-up rate limits.** `/api/interest` keys its per-IP limits on the **first X-Forwarded-For hop**, exactly as uvicorn does under `--forwarded-allow-ips='*'`: Railway's edge writes the client it accepted first and leaves any caller-supplied values after it (verified 2026-09-06 on QA — uvicorn logged the real client for spoofed headers, and the probe below limited the sixth request with one header line and with two). The header is trusted from any peer, as that uvicorn flag already implies; only Railway's edge and the project's private network reach the api. Re-run both passes against QA whenever Railway's networking changes. Each pass writes up to 5 rows into QA's `interest_signup` and spends 6 of the operator IP's 30/day budget, so at most five passes a day; expected `202 202 202 202 202 429` from each pass — **anything other than `202 ×5` then `429` (a sixth `202`, any `503`, a `429` before the sixth) means stop and investigate before any production deploy.**
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
