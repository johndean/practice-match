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
| `LOG_LEVEL` | ✓ | | `INFO` (the default; leave unset unless quietening a noisy deploy). The level `app/main.py`'s `_configure_logging` puts on the **`app`** logger hierarchy at app creation, which every module logger under `app.` inherits. Until 2026-09-12 NOTHING configured logging at all — not this repo, and uvicorn's own `LOGGING_CONFIG` touches only the `uvicorn*` loggers — so the root logger sat at its default `WARNING` with the last-resort handler and `railway logs --service api` showed uvicorn's access lines and nothing else: every `log.info` the api emits, including `app/api/market.py`'s structured boundaries cost line, went into the void while `log.warning` surfaced. One stderr stream handler, format `LEVEL logger: message`. uvicorn's three loggers are deliberately untouched. **An unknown value never takes the api down**: case and surrounding whitespace are normalised, the result is checked against `logging.getLevelNamesMapping()` (`DEBUG`, `INFO`, `WARNING`/`WARN`, `ERROR`, `CRITICAL`/`FATAL`, `NOTSET`), and anything else — `20`, `verbose` — **falls back to `INFO`** and is named once in a `WARNING` line at boot. Before that validator, `LOG_LEVEL=20` or even `INFO` with a trailing space raised `ValueError` inside `create_app()` at import and restart-looped the container. **api only** — the worker never calls `create_app()` and was never affected: `scripts/start.sh` already runs `celery … --loglevel=info`, which configures celery's own logging, so `app.tasks.census`'s INFO records have always reached the worker's log |
| `MAIL_FROM` | | ✓ | `VIN Foundation — Practice Match <no-reply@foundation.vin>` — the Resend sender. `foundation.vin` is the sender domain only (spec §2); changing it needs the matching Resend DNS records (Identity plan Task I6) |
| `MAIL_REPLY_TO` | | ✓ | `practicematch@vin.com` — **placeholder**. The mailbox replies to transactional email reach is an open item for the VIN Foundation (spec §10); set the real one before launch (Identity plan Task I6) |
| `VIN_FOUNDATION_POSTAL_ADDRESS` | ✓ | ✓ | The VIN Foundation's official postal address, printed in the launch email's CAN-SPAM footer (`VIN Foundation · {address}`). John sets it; never invented and never a placeholder (controller amendment A-I5d.4, 2026-09-08 — "Do not invent the address"). Optional at boot: `POST /api/admin/signups/launch-mail` refuses a real send with `409 LAUNCH_MAIL_NOT_CONFIGURED` while it is unset, rather than sending a footer with a blank address line |
| `RESEND_API_KEY` | | ✓ | **worker only** — the Resend API key. John holds it; never in git, chat, or CI, same rule as `CENSUS_API_KEY`. `railway variable set RESEND_API_KEY=… --service worker --environment <env>`. A worker without it raises on every `mail.send` beat rather than leaving mail silently queued (Identity plan Task I6) |
| `RESEND_WEBHOOK_SECRET` | ✓ | | **api only** — the `whsec_…` signing secret Resend shows when the endpoint `https://<host>/api/webhooks/resend` is created. Same handling rule. Unset, the route answers `401` to every call rather than trusting one (Identity plan Task I6) |
| `CENSUS_API_KEY` | | ✓ | Sub-project 3; John holds it — never in git, chat, or CI. `railway variable set CENSUS_API_KEY=… --service worker --environment <env>` |
| `CENSUS_CONTACT_EMAIL` | | ✓ | Sub-project 3 — the VIN Foundation's designated technical contact address, carried in the Census `User-Agent` (A-C1 ruling 4); never a developer's own. Required before the ingest worker's first live load — the load refuses to run without it |
| `S3_ENDPOINT_URL` | ✓ | ✓ | Sub-project 3 (A-C2) — the S3-compatible endpoint for Railway bucket `practice-match-data`, from `railway bucket credentials`. `api` reserves it for future tile reads; only the worker uses it today |
| `S3_BUCKET` | ✓ | ✓ | `practice-match-data` in every environment — Railway buckets are environment-scoped, no `-qa`/`-prod` suffix |
| `S3_ACCESS_KEY_ID` | ✓ | ✓ | Railway bucket credentials, set by the controller after John's demo — never printed. `ObjectStore.from_settings` returns `None` (object store disabled, logged) until all four `S3_*` variables are set |
| `S3_SECRET_ACCESS_KEY` | ✓ | ✓ | Same handling rule as `S3_ACCESS_KEY_ID` — never in git, chat, or CI |
| `PERSONA_PASSWORD` | | | **Not read by any service.** `scripts/seed_persona.py` reads it from the shell, and only outside production: `PERSONA_PASSWORD=… ENVIRONMENT=qa poetry run python scripts/seed_persona.py`. Unset it and the script falls back to its own documented default (`scripts/seed_persona.py`'s `DEFAULT_PASSWORD`); held in the operator's macOS Keychain (service `practice-match-qa`, account `PERSONA_PASSWORD`; read with `security find-generic-password -a PERSONA_PASSWORD -s practice-match-qa -w` into a subprocess environment, never printed); read by no service; passed to the seed and the harness through the shell; never on production (A-S6.2, superseding A-S6.1) (Identity plan Task I5) |
> **Setting a variable is not the same as the process seeing it.** `railway variable set … --skip-deploys`
> writes the value but leaves the running container with its old environment, so a job started with
> `railway ssh` afterwards still sees nothing. Either omit `--skip-deploys`, or run
> `railway redeploy --service <svc> --environment <env> --yes` and re-check from inside the container
> before relying on it (2026-09-10: the first Census load failed this way, silently, on all four `S3_*`).


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

**Numbering is reserved by plan, and a new file must take a free range.** `001`–`002` are the
original platform migrations · `010`–`015` Sub-project 2 (identity) · `016` the Seed Listings plan
· **`017`–`059` the Census plan's Sub-project 3 Phase A** and **`060`+ its Phase B** (that plan's
D14) · `080`–`089` the map engines · **`090`–`099` platform and hotfix migrations on `main`**
(A-L12, 2026-09-09 — `090_listing_photo_captions.sql` is the first). `003`–`009` are unassigned and
may only be taken by a platform migration that depends on nothing later.
`scripts/migrate.py` applies files in FILENAME order, so a file may only be numbered above
everything it depends on; the test suite applies the whole ladder into a fresh database on every
run, which is where a mis-numbered dependency fails.

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

The twenty-nine demo hospitals (`seeds/hospitals.json`) are loaded by
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

Run `scripts/seed_persona.py` **first**: they are assigned to
`seller@practice-match.test` at seed time (spec 2026-09-08 D25), and if that account does not
exist yet the import still succeeds with `seller_id` NULL and says so on stdout. `--owner <email>`
overrides the default and `--no-owner` seeds unowned; on production the default is not applied at
all unless `--owner` is passed.

**A listing the seller has edited is never re-seeded (A-SL21, 2026-09-09).** They belong to
`seller@practice-match.test`, so they open in the seller's own wizard — and the first seller write of
any kind (a wizard step saved, a photograph added, reordered or deleted, a document uploaded, submit,
pause, republish or withdraw) flips that row's `source` from `seed` to `seller`, in the same
transaction as the write. Every part of this importer is scoped `source = 'seed'`, so from that
moment the row is the seller's: it is not rewritten, its status is never reset to `published` behind
the reviewer's back, and `--reset` neither deletes it nor cascades away the photographs and documents
they uploaded onto it. Each run says how many it left alone — `skipped N seller-owned` on the summary
line, with the slugs named beneath it — and the untouched hospitals refresh as usual. A seed slug held
by a listing that belongs to NOBODY is a different thing and still stops the whole import (exit 5
below).

**The photographs (A-L9, revised by A-L10, and by A-L11 on 2026-09-09).** **Every photograph John
supplies is rendered — 313 of them today, 8 to 18 per hospital.** Positions **1-6** are the six
captioned slots the design's detail page renders (`photoSet(p)` in `Practice Match V3.dc.html`: an
exterior plus five subjects chosen by practice type); everything after them is an extra tile,
appended to the same grid by amendment A15 and counted by the docked panel's carousel. The caption
under one of the design's six is the DESIGN's own, fixed per slot, so the photograph at that
position has to show that subject — but a photograph now also carries its OWN description, and
that wins where there is one.

**Where a description comes from.** Today it is the **supplier's own filename** —
`06_interior_reception_lobby.png` becomes "Interior — reception lobby" — recorded per photograph in
`index.json` by `scripts/prepare_photos.py`, stored in `listing.photo_captions` (migrations/090) by
the seeder, and served beside `photos` by the API. A photograph with none falls back to the
design's fixed slot caption, and past the sixth slot — where the design has no caption to lend —
to "Photo N".

**A seller's own words are the other home (A-SL20, A-SL23 (0)).** A photograph the seller uploads
in the wizard's photo step carries the sentence they write for it in `listing_asset.caption`
(migrations/033), keyed by the asset — `listing.photos` holds that asset's uuid rather than a
path, so there is no position for the seeder's column to describe it at. `serialise` reads both
homes into the one `photo_captions` array a buyer is served, the seller's own words winning where
both have something to say. A caption is therefore STORED, wherever it was written; the DESIGN's
own fixed slot caption is a FALLBACK held in the design file, and it is what a photograph nobody
has described still renders under.

**`seeds/hospitals/photos/curation.json` is the source of truth for which photograph fills which
slot.** It was written by looking at every source image, because John's filenames do not reliably
describe their contents (one folder's `06_interior_reception.png` is a photograph of an exterior
sign) and several files are sliced fragments of a collage sheet. For every slug it names it is
authoritative for the slots it fills; a slot whose value is `null` has no truthful photograph in
that folder, and since A-L11 one of the folder's other SINGLE photographs fills it rather than the
slot standing empty. A slot **stays empty** — where the design renders its own placeholder — in two
cases: a folder holding fewer images than the design has slots (which no seeded hospital does), and
a folder whose remaining images are all multi-panel sheets. **A composite never occupies one of the
six captioned slots, even when that leaves the slot empty** (Task SD1 fix round 1, C1): a sheet of
six pictures is not "the reception area", and absent beats faked. Twenty-one slots across seven of
the eleven Dallas hospitals are empty for that reason today. Nothing is dropped — every sheet still
takes a position past the sixth, where amendment A15.3 renders it as a tile of its own.

`scripts/prepare_photos.py` writes `seeds/hospitals/photos/<slug>/<k>.webp` — **the number is the
position**, so positions 1-6 are the design's slots (`p.photos[i]` still fills slot `i`) and 7, 8, …
are the photographs beyond them — plus the `index.json` beside them, which carries one entry per
position with its `source`, its `caption` and the `slot` it fills (`null` past the sixth). Both
files and the curation are committed to the repository and baked into the image. The seeder uploads
no bytes — it records the relative paths positionally, with a JSON `null` for an empty slot, and the
`api` service serves the files off disk at `/api/listings/{id}/photos/{n}` (an empty slot is a 404
there, and the API sends `null` rather than a URL for it, so nothing requests it). Re-run
`poetry run python scripts/prepare_photos.py` only when the source folders or the curation change;
it needs Pillow (a dev dependency), prints `N files, M empty slots, K beyond the design's six
slots` (313, 21 and 160 today), and is never part of a deploy.
A curation entry that names a hospital the seed file does not, lists slots that are not the
practice type's list in order, names a file the folder does not hold, or uses one file for two
slots stops the run with exit 2 before anything is written.

**`seeds/hospitals/photos/descriptions.json` is where a photograph's own words come from when its
filename has none (Task SD1, 2026-09-10).** John's eleven Dallas folders are named
`alpha_dallas_01.png`: the filename says nothing about the picture, so `caption_of` has nothing to
read and the keyword path has nothing to match. This file carries, per source filename, the
description a reader produced by LOOKING at the image, and `prepare_photos.py` writes it as that
photograph's `caption` in `index.json` — which becomes `listing.photo_captions` and then
`p.photoCaptions[i]` (amendment A15). A photograph with no entry here keeps the filename caption,
which is what John's eighteen of 2026-09-06 have always had, so the file is optional: absent means
"nobody described these", not an error. An entry naming a file the folder does not hold stops the
run with exit 2, exactly as a curation entry does.

Each entry may also carry `flags` — what the content verification noted about identifiable content
in that image. They are **recorded, never acted on here**: they reach `index.json` so the image
identifiability work (A-IDP-1..6, its own branch) inherits the finding instead of re-reading every
image, and they decide nothing about what is DISPLAYED. Every seed still defaults to NOT SHOW
(A-IDP-4, corrected by A-IDP-6), and this seeder writes no column that says otherwise. A
photograph nobody flagged carries no `flags` key at all, so the entries already committed for the
eighteen do not move.

**A rendered street number is part of the invented identity, not grounds to leave a photograph
out.** John ruled on 2026-09-10, verbatim: *"the numbers are part of the hospital name and should
be 'shown/not shown' too"*. So a number worn as signage in one of these images is governed by the
listing's one `identifiable_content_visibility` switch and redacted under `NOT_SHOW` exactly as
the name is — never withheld as a file (controller ruling A-IDP-7, which adds a `premises_number`
regex class to the identifiability specification so the pipeline can detect it).
`alpha_dallas_05.png` was refused earlier that day and is restored on this basis.
`address_not_this_listing` is the seventh flag, added by the same ruling: an image rendering a
COMPLETE street address — number and street name — that is not this listing's own. John's words
reach the number, not the street name, so that residual is carried as a flag and as one open
question rather than as a refusal.

**No number in this set is a per-hospital fact.** Charlie's differs between its own renders
(`_01` reads 1010, `_03` and `_11` end in a narrow stem) and Juliet's glass door reads 22113 where
its keystone and pilaster read 2211; three of the eleven render no number at all. Each number is
therefore a property of its individual image, recorded in `note` and **never** as data — no
column, no constant, and no rewriting of a listing's `street` to match a sign.

**The flags are the pipeline's expectation set, not decoration.** Each names the detector outcome
the identifiability work is expected to produce on that image, which is what makes the eleven its
first real fixture; the mapping is pinned both ways by
`tests/seeds/test_photo_inventory.py::test_every_flag_names_the_detector_class_the_pipeline_must_produce`,
so a new flag cannot be invented without deciding what the classifier must do with it. The flag
names are deliberately **not** the spec's detector class names and must not be renamed to match:
`own_business_name` and `own_street_number` assert PROVENANCE — that the identity is the
listing's own invention — which no detector class can express, and which is why these images are
in the set at all.

| seed flag | expected detector outcome |
|---|---|
| `own_business_name` | identity match on field `name` (exact / substring / distinctive) |
| `own_street_number` | regex class `premises_number` (A-IDP-7) |
| `address_not_this_listing` | regex class `address` |
| `civic_signage` | vision kind `signage`, expected NOT to identify the practice |
| `vehicle_no_legible_plate` | vision kind `vehicle` |
| `certificates_text_unreadable` | vision kind `document` |
| `composite` | none — a slot-placement fact only |

**Adding a folder without rewriting the ones already committed: `--merge`.** Without it a run with
`--slugs` replaces the whole `index.json` with just those slugs — which is the right default,
because it is what makes a slug removed from `seeds/hospitals.json` disappear from the inventory
too. With `--merge` the run replaces its own slugs and leaves every other one byte for byte as it
was, which is how the eleven Dallas folders were added to the eighteen's tree without re-encoding
195 files:

```bash
poetry run python scripts/prepare_photos.py --source <staged folders> --merge \
  --slugs alpha_dallas_veterinary_specialist_hospital ...   # eleven slugs
```

Stage COPIES of John's folders under `<source>/<slug>_individual_images/` and run against those:
nothing under `~/Downloads` is ever modified, moved, renamed or deleted, and his own folder names
do not match the slugs (one has a trailing space; two spell "Dallas-Fort Worth" with a hyphen where
the seed file has an en dash).

**How it is actually run (A-L7 (3)):** locally, against the QA PostGIS service's public URL, with
`ENVIRONMENT=qa` and that URL handed to the process in its environment and never printed (the
script reads only `DATABASE_URL` and `ENVIRONMENT`; the `api` service's `DATABASE_URL` is the
`.railway.internal` private URL, unreachable off-platform — the PostGIS service's own variable is
the public one). `railway ssh` needs an SSH key on file for the CLI — the key `practice-match-cli`
is registered on this machine (A-C11 (1), 2026-09-09; this line previously, and incorrectly, said
no key was on file), so the in-container route below works directly, with no public URL to hand
around; the script, its idempotency and its output lines are identical either way.

```bash
railway status                                   # MUST print Project: Practice Match
DATABASE_URL="$(railway variable list --service PostGIS --environment QA --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["DATABASE_URL"])')" \
ENVIRONMENT=qa poetry run python scripts/seed_listings.py   # the PostGIS service's DATABASE_URL is its PUBLIC url; a VAR=… prefix keeps it out of argv
# first run:  "[seed] inserted 29, updated 0, removed 0, skipped 0 seller-owned" then "[seed] done - 29 listings"
# a re-run:   "inserted 0, updated 29, removed N, skipped S" — N being the seed rows the file no longer
#             carries, which every import deletes; the existing rows keep their ids.
```

The seeded hospitals are INSERTed directly as `published`, not created through the API, so they do not
trigger the automatic geocoding that published listings go through — after seeding, run the
`census_load.py geocode` step above (under "Census Phase A exit (QA)") to resolve their locations
and build market figures.

In-container (the `practice-match-cli` key on file):

```bash
railway status                                   # MUST print Project: Practice Match
railway ssh --service api --environment QA       # practice-match-cli key
python scripts/seed_listings.py                  # inside the container — the same operation
```

Only when fresh ids are actually wanted — it invalidates deep links and photo URLs, and since
A-L4 it buys nothing the plain import does not:

```bash
python scripts/seed_listings.py --reset          # "inserted 29, updated 0, removed 29, skipped 0 seller-owned"
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
the previous rows straight after a seed is that cache, not a failed import.

## Object storage

The seller's own photographs and documents — never the seed hospitals' — live in the
already-approved bucket `practice-match-data`, one per environment (Railway buckets are
environment-scoped, no `-qa`/`-prod` suffix; see the four `S3_*` rows above for the credentials).
`ObjectStore.from_settings` returns `None` until all four are set, and every seller upload is then
refused with `503 STORAGE_UNAVAILABLE` rather than crashing — a developer's machine or a fresh
environment still serves every READ (the seed hospitals' photographs come off disk and
need none of this) while only the WRITES stop.

Keys are `listings/<listing id>/photos/<asset id>.webp` for a photograph — every upload is
re-encoded to WebP with its metadata stripped (D15) — and `listings/<listing id>/documents/<asset
id><suffix>` for a floor plan, a financial packet or any other document, `<suffix>` being the
uploaded file's own extension. An asset is written once (`put_immutable`'s never-overwrite
guarantee) and deleted at most once; nothing under `listings/` is ever mutated in place.

The seed demo hospitals' own photographs are **not** in this bucket at all (D26): they are
committed under `seeds/hospitals/photos/`, already in the image, and served straight off disk by
the same guarded route a seller's own photograph is served by — object storage holds only what a
seller has uploaded.

## Census Phase A exit (QA)

**Runs in the worker container, never on this machine — `railway ssh --service worker`, never
`railway run` (controller amendment A-C11 (1), 2026-09-09, superseding the census plan's original
`railway run` step and `scripts/census_load.py`'s own former docstring).** `railway run --service
worker --environment QA -- python scripts/census_load.py …` executes **locally**, with the
worker's variables injected into this machine's process: that would pull `CENSUS_API_KEY`,
`CENSUS_CONTACT_EMAIL` and all four `S3_*` bucket credentials onto the operator's laptop — directly
against A-C1 ¶8, which stores the key only as a Railway secret, and against CLAUDE.md's rule
naming `CENSUS_API_KEY` as the one variable that must never leave Railway — and it would then fail
anyway on connect, because the worker's own `DATABASE_URL` is the `.railway.internal` private URL
(see "How it is actually run" above). The key `practice-match-cli` is registered on this machine,
so the in-container route below is available.

The controller runs this sequence **only on John's explicit word** — never on its own initiative,
and never as part of a routine deploy. Every subcommand is idempotent, so a failed step can simply
be re-run once fixed.

```bash
railway status                                        # MUST print Project: Practice Match
railway ssh --service worker --environment QA
```

**`PYTHONPATH=/app` is required, and this is not optional or cosmetic.** Python puts the SCRIPT's
own directory (`/app/scripts`) on `sys.path`, not the working directory, so a bare
`python scripts/census_load.py …` inside the container dies immediately with
`ModuleNotFoundError: No module named 'app'`. Every command below carries it. (Found on the first
real load, 2026-09-10: the earlier form had never been run against a deployed container.)

Inside that shell, the load order matters — TIGER first, because `zbp` refuses without the ZCTA
boundaries TIGER writes to `geo_area`:

```bash
env PYTHONPATH=/app python scripts/census_load.py tiger
env PYTHONPATH=/app python scripts/census_load.py acs      # all three ACS datasets: acs5, acs5_subject, acs5_prior
env PYTHONPATH=/app python scripts/census_load.py cbp
env PYTHONPATH=/app python scripts/census_load.py zbp
env PYTHONPATH=/app python scripts/census_load.py qwi      # resolves the latest published quarter, then trims to 20
env PYTHONPATH=/app python scripts/census_load.py bds --year 2022
```

Check each exit code against the shared scheme (`0` done · `2` refused before anything opened,
e.g. a licence gate or a missing prerequisite · `3` database unreachable or failed · `4` a
download/fetch failed · `5` validation failed) and stop on the first non-zero — nothing later
depends on a partial load, and every table is an idempotent upsert.

Then activate, one dataset at a time, each with its own reviewed note — `--force` needs both
`--note` and John's word, never one without the other:

```bash
env PYTHONPATH=/app python scripts/census_load.py activate tiger_cb      2023        --by john --note "…"
env PYTHONPATH=/app python scripts/census_load.py activate acs5          "2019–2023" --by john --note "…"
env PYTHONPATH=/app python scripts/census_load.py activate acs5_subject  "2019–2023" --by john --note "…"
env PYTHONPATH=/app python scripts/census_load.py activate acs5_prior    "2014–2018" --by john --note "…"
env PYTHONPATH=/app python scripts/census_load.py activate cbp           2022        --by john --note "…"
env PYTHONPATH=/app python scripts/census_load.py activate zbp           2022        --by john --note "…"
```

> ### After activating `tiger_cb`, check the log for silently-lost place names
> The Community Context card's Growth tile names the geography its figure was measured at —
> "Dallas", "Orange County" — by joining each listing's stored `place_geoid`/`county_geoid` to
> `geo_area` **at the currently active `tiger_cb` vintage**. `practice_location` carries no vintage
> of its own, so a listing geocoded against one edition may hold a geoid the next edition does not
> define. The listings route still answers 200 and the card still renders — a page that fails is
> worse than a name that is missing, the same ruling that removed the `float(None)` 500 — and the
> api log says so:
>
> ```bash
> railway logs --service api --environment <env> --lines 200 | grep "no geo_area name at the active tiger_cb vintage"
> ```
>
> **Run that after every `tiger_cb` activation.** Nothing else surfaces it: the tile simply stops
> naming its geography while `community_label` keeps describing the ring, every gate stays green,
> and no screen says anything is wrong. If the grep returns rows, the geoids need re-resolving at
> the new edition before the vintage is announced as live.

Then geocode every listing to its practice location, building catchments and figures for display
(figures need the active vintages first, so this step comes after `activate`):

```bash
env PYTHONPATH=/app python scripts/census_load.py geocode               # resolves every listing without a practice_location
env PYTHONPATH=/app python scripts/census_load.py geocode --listing <id>  # resolve one specific listing by id
env PYTHONPATH=/app python scripts/census_load.py geocode --force       # re-resolve listings that already have a location
```

The command is idempotent — it skips listings that already have a location and exits 0 when there is
nothing to do, so it can be safely re-run repeatedly. The seeder does not enqueue this step itself:
it is a bootstrapping tool that runs where no worker may be listening, and silently queueing work
nothing will consume is worse than not queueing it. A listing published through the API automatically
goes through this geocoding pipeline; seeded listings created via direct INSERT do not, which is why
the manual step is needed after seeding.

**What the automatic trigger covers, and what it does not (Task GEO-WIRE).** Publishing a listing
— the reviewer's `POST /api/admin/listings/{id}/decide` with `action: "publish"`, or the seller's
own `republish` — enqueues `census.geocode_listing` by name, after the transaction commits, when
the listing has no `practice_location` row. That enqueue is **deduped on the listing id for 600
seconds**, because the row it checks for is written by the worker: without the dedupe, every
publish inside the window between the enqueue and that write queued the same listing again. So a
second publish a minute after the first enqueues nothing. Read that two ways, not one: usually it
means the first enqueue is still in flight and there is nothing to do, but if the listing **still
has no pin after ten minutes** the first task failed and the dedupe is now the only reason a
re-publish does not retry — **re-run `census_load.py geocode`** (the plain form, with no flags: it
selects exactly the listings that have no `practice_location` row, so it retries the failures and
touches nothing else), and read the worker log for the reason it failed the first time. The one
thing that re-arms the trigger early is an address edit: when a seller **changes the city or the ZIP** at
step 2 of the wizard, the listing's `practice_location` row is deleted in the same transaction and
the dedupe key is dropped, so the very next publish resolves the new address. Everything else
about the listing — a new price, a new photograph, a disclosure switch — leaves the geography
alone, because the practice has not moved.

**What a seller's own listing is served, and why the demo hospitals are not.** The wizard collects
a city and a ZIP and no street, so the Census geocoder cannot match an address and the fallback
ladder resolves at `zcta` — a ZIP-code centroid, which in a large ZIP is miles from the practice.
A listing like that is served its Census place rather than the ring for its Community Context
figures (the controller's ruling, GEO-WIRE fix round 1), so its card shows a city figure and no
"Within about 5 miles of the practice" heading — **its city where the ZIP centroid lies in one;
otherwise the county carries growth and payroll and the area figures are unavailable** and the card
reads "Community data unavailable". That second case is unincorporated territory, and it is
correct rather than broken: `SELECT l.slug, pl.geo_precision, pl.place_geoid FROM listing l JOIN
practice_location pl ON pl.listing_id = l.id WHERE pl.place_geoid IS NULL;` is the list of listings
in it. By contrast all twenty-nine demo hospitals carry a street and resolve at `rooftop`, so their
cards keep the catchment ring they have today and nothing about them changes.
`SELECT geo_precision, count(*) FROM practice_location GROUP BY 1;` is how to see which listings on
an environment are in which case.

The geocode writes **both** point columns from one resolved coordinate: `practice_location.point`,
which every market figure is computed against, and `listing.geom`, which is the pin
`GET /api/listings` serves as `lat`/`lng` (still blanked for a listing whose seller has not
disclosed its location). `scripts/seed_listings.py` still writes the seeds' own points on every
import, and re-asserts them on the UPDATE half, so a re-seed restores a curated pin; the two
writers write the same column in the same SRID. Nothing above changes the demo hospitals: they
already carry a `practice_location` row, so the plain `census_load.py geocode` skips them. TWO
flags re-resolve a row that already has a location, and both will replace a curated seed pin with
the Census geocoder's own match: `--force` does it to every listing, and `--listing <id>`
re-resolves the listing it names whether or not it already has one. Neither is needed to pick up
anything in this release.

The vintage string must match what was ingested exactly, en dash included. `bds` and `qwi` have no
`activate` step in this sequence — `qwi`'s vintage is `<year>Q<quarter>` and `bds`'s is the year;
activate them only if the controller wants them pinned. Finally, `GET /api/admin/data-sources` on
qa.foundation.vin shows every dataset with its licence status, last run and active vintage.
Production stays gated (`MARKET_DATA_PUBLIC` false, A-C1 ¶10; the key gated per A-C1 ¶8).

**Phase B (listing-dependent market data) has its own integration contract, not a second runbook
here**: `docs/integrations/market-data-api.md` documents the member-gated `/api/layers`,
`/api/markets`, `/api/markets/{cbsa}/communities` and `/api/listings/{id}/market` routes, the
admin Data Sources console above, the licence gates each figure carries, and — corrected there,
not here — the Phase B exit checklist's per-dataset licence-flip verification (`zbp` for `vets`,
`cbp` for `econ`, `acs5` for the two figures Task B6 closed a licence hole on). The ingest/activate
sequence above is unchanged by Phase B; nothing here is repeated in that document.

## National Census loads and the `geo_metric` materialise — runbook

Seven rules, drafted 2026-09-12 from failures measured the same night — **every one of them was
learned by breaking it**. They govern any `scripts/census_load.py` run and any manual
`materialize_geo_metrics()` on the QA or production worker, and they sit here rather than in a
plan because a precondition that lives only in a working document is one somebody will not read.
`tests/test_docs.py::test_deploy_md_carries_the_national_census_loads_runbook` keeps them here.

### Rule 1 — a long load runs detached, or the ssh session kills it

`railway ssh --service worker -- <command>` ties the child to the session. When the session ends —
including when the CLI returns early, which it does — the child dies, and **`railway ssh` reports
exit 0 regardless**. The first national TIGER load (108 requests, ~6 minutes) was killed this way in
under a minute, left an `ingest_run` row orphaned at `running`, and reported success.

Run every load detached, inside ONE single-quoted `bash -c`, with stdin closed:

```bash
railway ssh --service worker --environment QA -- bash -c 'cd /app && nohup env PYTHONPATH=/app python scripts/census_load.py tiger > /tmp/tiger.log 2>&1 < /dev/null & echo "PID $!"'
```

Do not pass the command's own flags as separate ssh arguments: `acs --dataset acs5 --levels 140`
passed that way was mangled into "unrecognized arguments: --levels 140" while the deployed
subparser plainly had the flag. Quote the whole command.

### Rule 2 — poll the LEDGER, not the process

`railway ssh` under concurrent sessions returns empty output often enough that a process poll
through it times out having learned nothing (`/proc/<pid>` checks returned neither ALIVE nor DONE
for thirty iterations while the process had in fact exited). The worker image also has no `pgrep`,
`ps` or `uptime`.

The reliable completion signal is the database. `railway run --service PostGIS` did not flake in
the same session:

```bash
railway run --service PostGIS --environment QA -- bash -c 'PGPASSWORD=$POSTGRES_PASSWORD psql -h $RAILWAY_TCP_PROXY_DOMAIN -p $RAILWAY_TCP_PROXY_PORT -U $POSTGRES_USER -d $POSTGRES_DB -X -A -F"|" -c "SELECT dataset_key, status, rows_written, request_count, started_at, finished_at FROM ingest_run ORDER BY started_at DESC LIMIT 5"'
```

`rows_written` and `request_count` are written at COMMIT: a `running` row carrying zeros says only
that the run has not finished. A row stuck at `running` with the process gone is an orphan; mark it
`failed` with the reason (guard the UPDATE by `id`, `status='running'` and `finished_at IS NULL`).

### Rule 3 — activation is usually not needed, and forcing it would be wrong

If a load writes MORE rows under a vintage string that is ALREADY in `active_vintage`, the new rows
are served the moment the transaction commits — the read path selects on the active vintage. Do not
`activate` again: its [0.8, 1.25] row-count ratio guard exists to catch a suspicious jump, and a
six-state → national load is a measured ~3× jump you would have to `--force` through. Record the
expected jump in the ledger instead.

### Rule 4 — growth needs BOTH vintages at the SAME level

`population_growth_pct` is a difference of `acs5` (2019–2023) and `acs5_prior` (2014–2018) at one
summary level. Loading the baseline nationally at place level while the current vintage is still
six-state at that level changes nothing: growth exists only where both do. Load both, at every level
the card and the map read: `--levels 160 050` for the card's place/county path, `140` for the map.

### Rule 5 — the national numbers, measured 2026-09-12

| load | rows | requests | wall time |
|---|---|---|---|
| `tiger` (all levels, 51 states) | 154,176 | 107 | 5 m 39 s |
| `acs --dataset acs5 --levels 140` | 590,800 | 51 | 16 m 49 s |
| `acs --dataset acs5_prior --levels 160` | 29,320 | 51 | ~1 min |
| `acs --dataset acs5 --levels 160 050` | 246,239 | 102 | ~8 min |
| `acs --dataset acs5_prior --levels 050` | 3,142 | 51 | ~1 min |
| `cbp` | 3,696 | 153 | ~1 min |
| `zbp` | 9,258 | 3 | ~1 min |
| `materialize_geo_metrics()` | 84,106 + 6,424 + 1,819 rows | — | ~9 min |

**`zbp` MUST BE RELOADED after `feat/layers` deploys (fix round 1, 2026-09-12).** The loader now
fetches a FOURTH NAICS key in the same pass — `00`, the all-industry total — because it is the
only way to tell a ZIP area whose veterinary count the Census WITHHELD (its rule: a category with
fewer than three establishments is not reported at ZIP level, but is counted in the sum total)
from one ZIP Code Business Patterns does not cover at all. Without those rows every withheld ZIP
is served as an absence, which on Dallas was 393 of 535 polygons. One more request, about a third
more rows, same wall time:

```
railway ssh --service worker --environment QA -- bash -c 'nohup env PYTHONPATH=/app python scripts/census_load.py zbp > /tmp/zbp.log 2>&1 < /dev/null &'
```

then `materialize_geo_metrics()` again (below) so `geo_metric.establishments` picks up the third
state. The reload is an UPSERT and the existing 541940/812910/459910 rows are rewritten in place.

The write path was `psycopg2.executemany`, one round trip per row; `execute_batch(page_size=100)`
is a measured 2.9× speedup and **is applied** as of `feat/layers` — the six-layer nightly measured
~20 s nationally (06:21:02 → 06:21:21 on QA).

After the loads: `python -c "from app.tasks.census import materialize_geo_metrics; print(materialize_geo_metrics())"`
on the worker (detached, per Rule 1). It returns `{"metrics": {metric_key: rows}}`; a layer at 0 means
a missing active vintage or an uncleared licence, not an error. After ANY `tiger_cb` activation, grep
the api log for `no geo_area name at the active tiger_cb vintage` (the I4 rule).

### Rule 6 — do not redeploy the worker inside the five minutes before a beat entry fires

`scripts/deploy.sh` redeploys `api` AND `worker`. A worker restart as celery beat is about to fire
kills or reschedules that tick silently. The entries, all UTC: `materialize-nightly` 03:00,
`geo-metric-nightly` 03:30, `sessions-purge-nightly` 04:30, `outbox-purge-nightly` 04:40,
`qwi-quarterly` 06:00 on the 15th of Feb/May/Aug/Nov, `license-audit-quarterly` 07:00 on the 1st of
Jan/Apr/Jul/Oct. If a deploy must land in a window, run the missed task by hand afterwards and say so
in the ledger — never assume the nightly ran because the clock passed it.

### Rule 7 — a manual `geo_metric` materialise runs DETACHED on the worker (Rule 1) and is polled in the TABLE (Rule 2)

The polygon table's only writer is `app.tasks.census.materialize_geo_metrics` (celery name
`census.materialize_geo_metrics`, beat entry `geo-metric-nightly` 03:30 UTC). It writes NO
`ingest_run` row, so `celery_app.send_task(...)` hands back a task id and nothing pollable — do
not use it. Run the function itself, detached, and read its own log; it prints one row count per
layer and bumps `market:geo:version` on commit so cached nulls expire:

`railway ssh` re-tokenises the command it is handed, so a `python -c "…"` with quotes inside a
quoted `bash -c` arrives as `nohup: missing operand` and NOTHING runs (measured 2026-09-12 06:17Z;
the table showed no new rows three minutes later). Deliver the snippet with no inner quotes at
all — base64 into a file, then run the file detached:

    B64=$(printf 'from app.tasks.census import materialize_geo_metrics\nprint(materialize_geo_metrics(), flush=True)\n' | base64 | tr -d '\n')
    railway ssh --service worker --environment QA -- bash -c "cd /app && echo $B64 | base64 -d > /tmp/geo_run.py && (PYTHONPATH=/app nohup python /tmp/geo_run.py > /tmp/geo.log 2>&1 < /dev/null &) && sleep 4 && grep -la geo_run /proc/[0-9]*/cmdline | head -2"

The `grep -la … /proc/*/cmdline` line is the liveness check (no `ps`/`pgrep` in the image; a
shell `for` loop is mangled the same way the quotes are). It prints a `/proc/<pid>/cmdline` path
while the run is alive and nothing once it has exited.

Then poll the TABLE via `railway run` (Rule 2) — one row per layer, `served` = rows with a value —
and read `/tmp/geo.log` on the worker only when `max(computed_at)` has stopped advancing:

    SELECT metric_key, count(*) AS rows, count(*) FILTER (WHERE NOT suppressed AND value_num IS NOT NULL) AS served, max(computed_at) FROM geo_metric GROUP BY 1 ORDER BY 1;

Never two writers at once: `materialize-nightly` 03:00 writes the LISTING table, `geo-metric-nightly`
03:30 writes THIS table — never start inside the five minutes before 03:30 or while a previous run's
`max(computed_at)` is still advancing. Three national layers took the nightly ~3.5 min (03:30:01 →
03:33:16 on 2026-09-12); budget ~8 for six.

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
