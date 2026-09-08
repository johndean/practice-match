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
| `HIBP_ENABLED` | ✓ | | `true` in every environment; Have I Been Pwned k-anonymity password screen — falls back to the bundled offline list on any error (never disabled to skip the offline fallback, only to skip the network call in constrained environments) |
| `MARKET_DATA_PUBLIC` | ✓ | | `false` — anonymous visitors gain `market.read` only while `true`; QA evaluation only, **never** production (Identity plan Task I3) |
| `CONSOLIDATOR_KEYWORDS` | ✓ | | comma-separated employer-domain keywords, VIN Foundation-supplied; an application-review hint only, never a decision — default empty |
| `LINK_BASE_URL` | ✓ | ✓ | `https://qa.foundation.vin` / `https://foundation.vin` — the origin the verify and password-reset links in transactional email point at; a wrong value sends people to the other environment (Identity plan Task I4) |
| `EMAIL_ALLOWLIST` | ✓ | ✓ | comma-separated **whole addresses** (not domains) transactional email may be delivered to on any non-production environment. Fail-closed: outside production an **empty** list delivers to **nobody** — every row is recorded `suppressed` — so QA test sign-ups cannot email real people. Ignored on production, which delivers to everyone (Identity plan Task I6) |
| `DB_POOL_MAX` | ✓ | ✓ | QA (set 2026-09-08): `10` on api, `4` on worker — the size of the psycopg2 **reuse pool** per DSN (`app/db.py`), which is what removes the per-request connect. uvicorn runs the api as a single process and celery runs `--concurrency=2` (`scripts/start.sh`) plus beat, so the two reuse pools together hold at most 14 idle connections against PostGIS's `max_connections` of 100. It does **not** cap how many connections exist: past the pool a caller gets an un-pooled connection rather than an error — that overflow is per call and closes on return, so the ceiling on backends is request concurrency, not this number. Bounding that overflow is Sub-project 2's concurrency work (Identity plan Task I9); raise this only if the pool is measured to be the bottleneck (Identity plan Task I4) |
| `MAIL_FROM` | | ✓ | `VIN Foundation — Practice Match <no-reply@foundation.vin>` — the Resend sender. `foundation.vin` is the sender domain only (spec §2); changing it needs the matching Resend DNS records (Identity plan Task I6) |
| `MAIL_REPLY_TO` | | ✓ | `practicematch@vin.com` — **placeholder**. The mailbox replies to transactional email reach is an open item for the VIN Foundation (spec §10); set the real one before launch (Identity plan Task I6) |
| `VIN_FOUNDATION_POSTAL_ADDRESS` | ✓ | ✓ | The VIN Foundation's official postal address, printed in the launch email's CAN-SPAM footer (`VIN Foundation · {address}`). John sets it; never invented and never a placeholder (controller amendment A-I5d.4, 2026-09-08 — "Do not invent the address"). Optional at boot: `POST /api/admin/signups/launch-mail` refuses a real send with `409 LAUNCH_MAIL_NOT_CONFIGURED` while it is unset, rather than sending a footer with a blank address line |
| `RESEND_API_KEY` | | ✓ | **worker only** — the Resend API key. John holds it; never in git, chat, or CI, same rule as `CENSUS_API_KEY`. `railway variable set RESEND_API_KEY=… --service worker --environment <env>`. A worker without it raises on every `mail.send` beat rather than leaving mail silently queued (Identity plan Task I6) |
| `RESEND_WEBHOOK_SECRET` | ✓ | | **api only** — the `whsec_…` signing secret Resend shows when the endpoint `https://<host>/api/webhooks/resend` is created. Same handling rule. Unset, the route answers `401` to every call rather than trusting one (Identity plan Task I6) |
| `CENSUS_API_KEY` | | ✓ | Sub-project 3; John holds it — never in git, chat, or CI. `railway variable set CENSUS_API_KEY=… --service worker --environment <env>` |
| `PERSONA_PASSWORD` | | | **Not read by any service.** `scripts/seed_persona.py` reads it from the shell, and only outside production: `PERSONA_PASSWORD=… ENVIRONMENT=qa poetry run python scripts/seed_persona.py`. Unset it and the script falls back to its own documented default (`scripts/seed_persona.py`'s `DEFAULT_PASSWORD`); held in the operator's macOS Keychain (service `practice-match-qa`, account `PERSONA_PASSWORD`; read with `security find-generic-password -a PERSONA_PASSWORD -s practice-match-qa -w` into a subprocess environment, never printed); read by no service; passed to the seed and the harness through the shell; never on production (A-S6.2, superseding A-S6.1) (Identity plan Task I5) |

## DNS (verbatim as Railway printed them — Task 8, 2026-09-06)

Both custom domains need **all four** records below, not just a CNAME each — Railway shows `Verified: no` / `CERTIFICATE_STATUS_TYPE_VALIDATING_OWNERSHIP` until the TXT ownership record also resolves. DNS changes can take up to 72 hours to propagate worldwide.

| Host | Type | Name | Value |
|---|---|---|---|
| `qa.foundation.vin` | CNAME | `qa` | `va7f7sbq.up.railway.app` |
| `qa.foundation.vin` | TXT | `_railway-verify.qa` | `railway-verify=7b12d7490dc75edd5a53905f248d52e61b37f924b8b680eb389966e22c11d9c4` |
| `foundation.vin` | CNAME | `@` (apex) | `iz4g9ph8.up.railway.app` |
| `foundation.vin` | TXT | `_railway-verify` | `railway-verify=dd94ec458f0f18d4ca0806f5e1803bc5371ba016976b18601e795ba3bedb5292` |

`foundation.vin`'s record is an **apex CNAME**, not the A record the plan originally expected — the DNS provider must support ALIAS / ANAME / CNAME-flattening at the root; a plain CNAME at the apex is invalid on providers without it. Check propagation with `dig +short qa.foundation.vin CNAME`, `dig +short foundation.vin CNAME`, `dig +short _railway-verify.qa.foundation.vin TXT`, `dig +short _railway-verify.foundation.vin TXT`, then `railway domain status a066b6b3-bca4-4cd8-bbfb-ae21d2a24531` (QA) / `railway domain status d9e291e7-498c-40a7-9fe3-f8b54c695986` (production). Until DNS is live, verify against the Railway-issued hosts directly: QA `https://api-qa-f3b3.up.railway.app`, production `https://api-production-ebcf.up.railway.app` (pass as `scripts/verify-deploy.sh ENV <url>` or set `VERIFY_BASE_URL`).

## Resend DNS (sender domain `foundation.vin` — Identity plan Task I6)

No transactional mail is delivered until the sender-domain records resolve and Resend shows the
domain verified: a verify link, a password reset and every application decision all go out through
it. Add `foundation.vin` in the Resend dashboard, then create the records it prints. **Every value
is copied out of the dashboard and lives nowhere else** — not here, not in git, not in chat, the
same rule as `RESEND_API_KEY` and `CENSUS_API_KEY`. John holds the account and fills these in.

| Purpose | Type | Name | Value |
|---|---|---|---|
| DKIM 1 of 3 | CNAME | `<selector1>._domainkey.foundation.vin` | value from the Resend dashboard |
| DKIM 2 of 3 | CNAME | `<selector2>._domainkey.foundation.vin` | value from the Resend dashboard |
| DKIM 3 of 3 | CNAME | `<selector3>._domainkey.foundation.vin` | value from the Resend dashboard |
| SPF | TXT | `send.foundation.vin` | value from the Resend dashboard |
| DMARC | TXT | `_dmarc.foundation.vin` | value from the Resend dashboard |

The DKIM selectors are generated per domain, so the `<selectorN>` labels above are placeholders too
— read them off the dashboard with the values. **Copy the set the dashboard actually shows**: if it
asks for a different shape (a single `resend._domainkey` TXT beside a `send` MX and SPF pair, which
is the other form Resend uses), create that and correct this table in the same commit rather than
forcing the rows above. Check propagation the same way as the Railway records —
`dig +short <selector1>._domainkey.foundation.vin CNAME`, `dig +short send.foundation.vin TXT`,
`dig +short _dmarc.foundation.vin TXT` — and confirm "Verified" in the dashboard before expecting a
single email to arrive. One sender domain serves both environments; QA is kept from emailing real
people by `EMAIL_ALLOWLIST`, not by a separate domain.

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
| `exit 64` | usage: the environment is not `QA`/`production`, or SOURCE_DIR is not a directory, not a git working tree (a bare repository and a bare `.git` directory are not), has no commits, or its committed tree carries no readable `[project].version` | fix the arguments; every one of these says which |
| `exit 65` | 🚦 the linked Railway project is not **Practice Match** | `railway link`, then `railway status` |
| `exit 66` | SOURCE_DIR has uncommitted changes to tracked files — the upload is HEAD, so those edits would silently not ship | commit them, or pass a SOURCE_DIR that is committed. Untracked files are fine and are simply left out |
| `exit 67` | the upload created no deployment, or the deployment did not reach `SUCCESS` | read the message: either the upload itself failed and **nothing was deployed**, or `railway logs --service <svc> --environment <env> --lines 100` |

The 67 path exists because `railway up --ci` streams build logs and that stream can time out (`reqwest error … operation timed out`) *after* the upload succeeded, while the deployment carries on — aborting there would leave the api deployed and the worker not. A non-zero `up` is therefore resolved by asking Railway what actually happened, and it **fails closed**: the newest deployment's `createdAt` is recorded *before* the upload, and a deployment with a **strictly newer** `createdAt` must appear within 120 s or the script exits 67 with `upload did not create a deployment for <service>`. That guard matters because `up` also exits non-zero when the upload itself failed, and then Railway's newest deployment is still the previous deploy's — very possibly a `SUCCESS`, which a status-only poll would misread as this deploy succeeding. A deployment whose JSON carries no `createdAt`, or one this script cannot parse as a moment, cannot be dated and so reads as "no new deployment" (67) rather than being trusted or waited on for ever — `createdAt` is compared as a parsed instant, not as text, so one offset-format row in the list cannot silently mis-order it. Once identified, that deployment and only that one (by `id` where the CLI supplies one) is polled to `SUCCESS` — continue to the next service — or to any terminal status that is not SUCCESS (`FAILED`, `CRASHED`, `REMOVED`, `SKIPPED`, `CANCELLED`), which ends the wait at once with 67 rather than burning the 15-minute bound. `DEPLOY_POLL_INTERVAL` / `DEPLOY_APPEAR_TIMEOUT` / `DEPLOY_POLL_TIMEOUT` override the 10 s / 120 s / 900 s bounds; the shell tests set them to seconds.

Expected `verify-deploy.sh` output on QA (app mode): `healthz OK  version X.Y.Z  commit <sha>  postgis 3.5.x`, `deep healthz OK`, `config OK  market_data_public False`, `SPA fallback OK`. On production in coming-soon mode the script is site-mode aware: it reads `site_mode` from `/api/healthz` and swaps the SPA check for the coming-soon shell and the launch-notification endpoint — `healthz OK  version X.Y.Z  commit <sha>  postgis 3.5.x  site_mode coming_soon`, `deep healthz OK`, `config OK  market_data_public False`, `coming-soon shell OK`, `interest endpoint OK` (no `SPA fallback OK` line in this mode). The `config OK` probe (Identity Task I7) reads the public `GET /api/config`, which the browser itself reads before `/api/me` on every page load: it must answer 200 with a JSON **boolean** `market_data_public`, and on **production** that boolean must be `false` — `MARKET_DATA_PUBLIC` is a QA evaluation flag and never production's, so `true` there fails the deploy. On QA either value passes; evaluating the flag is what QA is for. Boot lines to look for in `railway logs --service api --environment <env> --lines 50`: `[start.sh] role=api`, `Uvicorn running on http://0.0.0.0:<port>`; on the worker: `[start.sh] role=worker`, `celery@… ready`, `[worker-health] listening`.

**Nightly load smoke baseline** (`.github/workflows/perf.yml`, first manual run from `main`, 2026-09-06, 20 virtual users × 2 min against `https://qa.foundation.vin/api/healthz` — the only endpoint until Sub-project 2): p95 = 174 ms (budget 400 ms), median 118 ms, 22 054 requests, 0 % errors. Compare later runs against this line.

**`SKIP_VERIFY=1 scripts/deploy.sh <env>`** skips the automatic `verify-deploy.sh` call at the end of `deploy.sh`. It exists only to sequence the very first deploy of a brand-new commit (e.g. deploying `api` and `worker` back to back without the first one's probe racing the second's rollout) and must never be habitual — Railway's own healthcheck passes on an always-200 `/api/healthz` regardless of the database or Redis being reachable (Task 8 proved this: the first QA attempt was green in Railway with the database unreachable), so `scripts/verify-deploy.sh` is the only gate that actually reads component state (`db.ok`, `postgis_version`, the `/deep` endpoint's 200). Always let it run; only skip it deliberately, and always run it by hand immediately after if you do.

**`EXPECT_SHA`** is the commit `scripts/verify-deploy.sh` requires the live `/api/healthz` to report, so a stale container that answers 200 with yesterday's code fails the deploy: unset or empty both fall back to this checkout's `git rev-parse --short HEAD` (the script's `${EXPECT_SHA:-…}` cannot tell an empty value from an absent one), a non-empty value is compared verbatim, and the assertion is skipped only when the script runs outside a git checkout, where `git rev-parse` yields nothing to compare against. When the branch has moved past the tree that is actually deployed, pass the deployed commit explicitly — `EXPECT_SHA=087acc1 scripts/verify-deploy.sh QA` — because the default would otherwise demand a HEAD that was never shipped.

**`EXPECT_VERSION`** is the release version the live `/api/healthz` must report, and it is the probe that proves the deployed **artefact** rather than a variable. `commit_sha` could not: it was the `COMMIT_SHA` service variable `deploy.sh` sets immediately before each upload, so it agreed with the deploy even in P14, when the tree that had actually been uploaded was a different one. `version` is read from the `pyproject.toml` *inside the image*, so a tree that is not the one we built shows up here — a mismatch fails with one `FAIL:` line naming both versions. `deploy.sh` passes the version of the tree it archived; run by hand the default is the version in the `pyproject.toml` beside the script, and (as with `EXPECT_SHA`) unset and empty behave identically, the assertion being skipped only when that file is unreadable or carries no version. **After deploying a SOURCE_DIR other than this checkout**, both defaults are wrong for a hand-run verification — the verifier would demand this checkout's version and sha and report `FAIL: version is …, expected …` against a perfectly good deploy — so re-run it as `EXPECT_SHA=<sha> EXPECT_VERSION=<version> scripts/verify-deploy.sh QA`, with the sha and version of the tree that was archived. `scripts/deploy.sh` prints that exact line, filled in, after every successful deploy. `commit_sha` is now an artefact property too: it is the contents of `/app/BUILD_SHA`, a file `deploy.sh` writes into the archive and the Dockerfile copies, falling back to the `COMMIT_SHA` variable only when the image carries no stamp (a git-connected Railway build, or a local `docker build`).

## Migrations

**An applied migration is immutable.** From `f3b7d41` the ledger records each file's SHA-256 alongside its name, and a file whose bytes have changed since it was applied stops the container before uvicorn with exit 4 (`[migrate] <file> changed after it was applied — drop and recreate the database or restore the file`) — so amend a numbered file in place only while no persistent database has yet run it, which today means only files added after `b9d01ad`: QA and production predate Wave 2a and neither is affected. Enforcement begins with the files applied from `f3b7d41` onward and is not retroactive: ledger rows written before it carry no checksum and are not checked, so `001_init.sql` and `002_interest_signup.sql` — already applied on QA and production — stay unchecked and must simply be left alone.

## Identity operations (Wave 2a)

The operator page is **[docs/RUNBOOK-identity.md](docs/RUNBOOK-identity.md)** — the review queue and
its decisions, role grants, the audit trail, an applicant who never got the email, a locked-out
member, rotating `RESEND_API_KEY`, and the QA persona accounts. Two of those are run from a checkout
rather than through the app, so they belong on this page:

* **The first admin** — `ENVIRONMENT=qa poetry run python scripts/bootstrap_admin.py --email person@example.org`
  creates (or reactivates) an `active` account holding `admin` with **no usable password** and prints
  a single-use 24 h invite link, which is the only way in. It refuses on production without
  `--production` (exit 2) and refuses an address already in `pending`/`needs_review`/`declined`/
  `suspended`/`revoked` without `--reactivate` (exit 3) — each of those is a recorded staff decision.
  Every run writes an audit row. **The link is a credential**: send it the way you would a password
  reset, never into a shared log.
* **QA persona accounts** — `PERSONA_PASSWORD=… ENVIRONMENT=qa poetry run python scripts/seed_persona.py`
  seeds the ten `.test` accounts the visual suite and a QA click-through use. Idempotent, and it
  **refuses on production with no override flag** (exit 2). `PERSONA_PASSWORD` is read from the
  shell by the script itself; held in the operator's macOS Keychain (service `practice-match-qa`,
  account `PERSONA_PASSWORD`; read with `security find-generic-password -a PERSONA_PASSWORD -s
  practice-match-qa -w` into a subprocess environment, never printed); read by no service; passed
  to the seed and the harness through the shell; never on production (A-S6.2, superseding A-S6.1).

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

**App-mode-only surfaces.** `app/main.py` mounts the auth, applications, `/api/admin/users`, `/api/listings` and (controller amendment A-I5d.5, John's ruling, 2026-09-09) `/api/admin/signups` routers only inside `if settings.site_mode == "app":` — every route on all five answers a plain `404` while production is still `coming_soon`, whatever credential is presented, `API_SECRET_KEY` bearer included. `scripts/verify-deploy.sh` probes all five on a coming-soon deployment, and `/api/listings` and `/api/admin/signups` on an app-mode one.

**Client address for the sign-up rate limits.** `/api/interest` keys its per-IP limits on the **first X-Forwarded-For hop**, exactly as uvicorn does under `--forwarded-allow-ips='*'`: Railway's edge writes the client it accepted first and leaves any caller-supplied values after it (verified 2026-09-06 on QA — uvicorn logged the real client for spoofed headers, and the probe below limited the sixth request with one header line and with two). A first hop that is not a valid IP address (`ipaddress.ip_address` refuses it) is not trusted as an address at all: it is bucketed as the single subject `unknown`, so a caller reaching the api off the edge cannot mint a fresh rate-limit bucket per forged header. The header is trusted from any peer, as that uvicorn flag already implies; only Railway's edge and the project's private network reach the api. Re-run both passes against QA whenever Railway's networking changes. Each pass writes up to 5 rows into QA's `interest_signup` and spends 6 of the operator IP's 30/day budget, so at most five passes a day; expected `202 202 202 202 202 429` from each pass — **anything other than `202 ×5` then `429` (a sixth `202`, any `503`, a `429` before the sixth) means stop and investigate before any production deploy.**
```bash
T=$(date +%s)
for i in 1 2 3 4 5 6; do curl -sS -o /dev/null -w "%{http_code} " -X POST -H 'Content-Type: application/json' -H "X-Forwarded-For: 203.0.113.$i" -d "{\"email\":\"probe-$T-a$i@example.invalid\"}" https://qa.foundation.vin/api/interest; done; echo; sleep 61
for i in 1 2 3 4 5 6; do curl -sS -o /dev/null -w "%{http_code} " -X POST -H 'Content-Type: application/json' -H "X-Forwarded-For: 198.51.100.$i" -H "X-Forwarded-For: 198.51.100.99" -d "{\"email\":\"probe-$T-b$i@example.invalid\"}" https://qa.foundation.vin/api/interest; done; echo
```

## Seeding the demo hospitals (QA)

The eighteen demo hospitals (`seeds/hospitals.json`, spec 2026-09-06 D7) are loaded by
`scripts/seed_listings.py`, which ships in the image together with `seeds/`. It is idempotent —
an upsert by `slug`, so the rows keep their ids and their photo URLs stay valid; the only columns
a re-run moves are `updated_at` and `listed_at`, the latter being
recomputed from `listed_days_ago` on every import by design (the seeds never read as a year old, and every row
shifts equally, so their relative order is preserved). **Every** run also deletes the
`source='seed'` rows the file no longer carries, in the same transaction as the upsert (amendment
A-L4). A `source='seller'` row is never touched, and a slug some other listing already owns stops
the whole import (exit 5 below). It is a hand operation, and it is
never on production without John's go — against `ENVIRONMENT=production` the script refuses
unless the operator says it out loud with `--production`, exactly as `scripts/bootstrap_admin.py`
does; with the flag, the run's first line of output names the environment it is writing to.

**How it is actually run (A-L7 (3)):** locally, against the QA PostGIS service's public URL, with
`ENVIRONMENT=qa` and that URL handed to the process in its environment and never printed (the
script reads only `DATABASE_URL` and `ENVIRONMENT`; the `api` service's `DATABASE_URL` is the
`.railway.internal` private URL, unreachable off-platform — the PostGIS service's own variable is
the public one). `railway ssh` needs an SSH key this machine does not hold, so the
in-container route below is for when a key is on file; the script, its idempotency and its output
lines are identical either way.

```bash
railway status                                   # MUST print Project: Practice Match
DATABASE_URL="$(railway variable list --service PostGIS --environment QA --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["DATABASE_URL"])')" \
ENVIRONMENT=qa poetry run python scripts/seed_listings.py   # the PostGIS service's DATABASE_URL is its PUBLIC url; a VAR=… prefix keeps it out of argv
# first run:  "[seed] inserted 18, updated 0, removed 0" then "[seed] done - 18 listings"
# a re-run:   "inserted 0, updated 18, removed N" — N being the seed rows the file no longer
#             carries, which every import deletes; the eighteen keep their ids.
```

In-container, when an SSH key is on file:

```bash
railway status                                   # MUST print Project: Practice Match
railway ssh --service api --environment QA       # John's ed25519 key; the CLI needs a key on file
python scripts/seed_listings.py                  # inside the container — the same operation
```

Only when fresh ids are actually wanted — it invalidates deep links and photo URLs, and since
A-L4 it buys nothing the plain import does not:

```bash
python scripts/seed_listings.py --reset          # "inserted 18, updated 0, removed 18"
```

And on production, with John's go and only then (`ENVIRONMENT` is already `production` inside
that container, so the flag is the whole difference):

```bash
python scripts/seed_listings.py --production
```

Exit codes: `0` — done · `2` — refused before anything was opened (`ENVIRONMENT` unset, or
`ENVIRONMENT=production` without `--production`, or `DATABASE_URL` unset) · `3` — database
unreachable, retry · `4` — the seed data is missing or malformed (fix the file, redeploy), or the
database refused the import: an **unmigrated database** is the usual cause, because the `seed`
role — unlike `api` — does not run `scripts/migrate.py` first, so run that and try again ·
`5` — a **non-seed listing** already owns one of the seed slugs; the message names them and
nothing was written, so decide with the seller (rename the seed slug, or withdraw their listing)
and run it again. A traceback is none of these: the data is safe either way — the whole import is
one transaction and rolls back — but the image is wrong.

The same run is available as a container role: `bash scripts/start.sh seed --reset`, for a
one-off Railway service command. `python -m scripts.seed_listings` works too, from `/app`.

`GET /api/listings` caches each page in Redis for 60 s and the seeder does not invalidate it, so
after a re-seed the list refreshes within a minute (Task L5, A-L5.1) — a browse that still shows
the previous eighteen straight after a seed is that cache, not a failed import.

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
