# Coming Soon production mode — design

**Date:** 2026-09-06 · **Owner:** John · **Scope:** Platform plan, new Task 11 (before Task 10's production step) · **Status:** approved in conversation 2026-09-06; spec for John's review

## 1. Decision

Production (`foundation.vin`) publishes the VIN Foundation **Coming Soon** page, not the Practice Match marketplace. QA (`qa.foundation.vin`) keeps the full marketplace. The coming-soon page never goes to QA — no exceptions. The marketplace launches on production later by flipping one variable and redeploying; no rebuild.

The page is John's Vue 3 project `coming_soon_vue` (a pixel-for-pixel conversion of the approved design `Coming Soon.dc.html`), delivered as a zip; its email form is front-end only and is wired to our API.

## 2. Serving: one image, one mode setting

- New setting `SITE_MODE` in `app/config.py`: `app` (default) or `coming_soon`; any other value fails fast at import like the other settings.
- The Docker image builds both frontends: the existing `frontend/` stage and a second stage for `coming-soon/` (Node 22, `npm ci && npm run build`), copied to `/app/coming-soon/dist`. `ENVIRONMENT` remains a required build arg.
- `app/static.py` mounts the dist selected by `SITE_MODE`: `frontend/dist` for `app`, `coming-soon/dist` for `coming_soon`. In coming-soon mode every non-API path serves that shell (`index.html`, `/assets/*`, `/ds/*`); fingerprinted output under `/_app/` (Vite `assetsDir` `_app`, matching the marketplace build) is immutable-cached; `/api/*` is unchanged. Unknown `/api/*` stays a JSON 404 in both modes.
- Indexing: the existing `PUBLIC_INDEXING` setting governs `X-Robots-Tag` and `/robots.txt`. Production sets `PUBLIC_INDEXING=true` (coming-soon is the public face); QA keeps it unset (noindex). The coming-soon `index.html` already carries a real `<title>` and `<meta name="description">`.
- `/api/healthz` gains one key, `site_mode` (`"app"` | `"coming_soon"`), appended to the existing exact key set. The health contract row in the Platform plan is amended accordingly.

Environment matrix:

| Variable | QA | production |
|---|---|---|
| `ENVIRONMENT` | `qa` | `production` |
| `SITE_MODE` | `app` | `coming_soon` |
| `PUBLIC_INDEXING` | unset (noindex) | `true` |

Launch later: set production `SITE_MODE=app` (and decide `PUBLIC_INDEXING`), `scripts/deploy.sh production`, verify in `app` mode. Documented in `DEPLOY.md`.

## 3. Sign-up endpoint

`POST /api/interest`, JSON body `{"email": "<address>"}` (the page has no consent checkbox; consent is the page's own promise — one message, never shared — recorded as `consent_version = "coming-soon-v1"` on every row).

- Normalise: trim, lowercase; validate with a conservative pattern (one `@`, a dot in the domain, no whitespace, ≤ 254 chars). Invalid → `422 {"error": "invalid_email"}` (generic; the page shows its own copy).
- Rate limits via Redis (the pooled client from `app/db.py`): 5 requests per minute and 30 per day per client IP (`X-Forwarded-For` first hop as Railway sets it, else peer address), and 3 per day per normalised address. Exceeded → `429 {"error": "rate_limited"}`.
- Store: table `interest_signup` (migration `002_interest_signup.sql`): `id uuid primary key default gen_random_uuid()`, `email text not null`, `email_normalised text not null unique`, `consent_version text not null`, `source text not null default 'coming-soon'`, `created_at timestamptz not null default now()`. Duplicate normalised address → no new row.
- Response: `202 {"status": "ok"}` for both a new and an already-registered address (no list enumeration). No email is sent; the Identity wave's Resend pipeline (Wave 2a) reads this table for the launch notification.
- Performance: `/api/interest` joins the latency budget table at p95 ≤ 100 ms (in-process, scratch DB).

## 4. Wiring John's page

The project is copied from the zip to `coming-soon/` at the repository root (no `node_modules`, no `dist`), with a lockfile generated and committed. Files stay byte-identical to the delivery except:

1. `coming-soon/src/logic.js` `submit()`: after its existing validation, `POST /api/interest`; on `202` → the existing confirmed state; on `429` → error text "Too many attempts — please try again later."; on any other failure (network, 5xx) → "Something went wrong. Please try again." in the existing error slot. Double submission is blocked while a request is in flight.
2. `coming-soon/index.html`: Merriweather is self-hosted (OFL) from `public/ds/fonts/` like Proxima Nova; the Google Fonts `<link>`s are removed. The README anticipates this ("self-host before launch"). No other file in the delivery changes; inline styles stay inline (the README's rule).
3. `coming-soon/vite.config.js`: `build.assetsDir = '_app'` so the static server's immutable-cache rule applies (the marketplace uses the same layout).

Favicon and Open Graph image (the README's "worth adding before launch") are John's assets; they are added when he supplies them, not invented.

## 5. Gates (test-first, no exceptions)

- **Pixel parity:** John supplies `Coming Soon.dc.html` (and its runtime support if separate); it joins `docs/design-reference/coming-soon/`. The Playwright harness serves it through the reference server and compares the rendered coming-soon page at `maxDiffPixels: 0` for the desktop and mobile viewports and the four form states (idle, invalid, confirmed, redacted hint advanced). A `coming-soon` Playwright project targets a local Vite dev server for `coming-soon/`; in CI both projects run.
- **Unit:** `coming-soon/src/logic.js` under vitest at 100 % lines/branches/functions/statements (same policy as `frontend/`; `fetch` stubbed at the network boundary; `dc-logic.js`, `hover.js` and `App.vue` are the delivered prototype and stay under the pixel gate).
- **API:** `tests/api/test_interest.py` — success, duplicate (202, single row), invalid address (422), rate limit per IP and per address (429), body shape; migration schema test; latency row.
- **Static/mode:** `tests/test_static.py` — `SITE_MODE=coming_soon` serves the coming-soon shell at `/` and any non-API path, `/api/*` 404 stays JSON, `_app` immutable, `assets`/`ds` short-cached; `SITE_MODE=app` unchanged; invalid `SITE_MODE` fails fast; `healthz.site_mode` reflects the setting.
- **Deploy verification:** `scripts/verify-deploy.sh` reads `site_mode` from the health body and, for `coming_soon`, asserts the served `/` carries `<title>VIN Foundation — Coming Soon</title>` and does not carry the marketplace shell; for `app` it keeps the existing SPA check. The shell test gains both cases.
- **Drift:** `.env.example`, `DEPLOY.md` and `CLAUDE.md` document `SITE_MODE`, the environment matrix and the launch flip; `tests/test_docs.py` asserts them.
- **Build:** `Dockerfile` builds both frontends; `tests/test_build_config.py` asserts the second stage and the copy; `scripts/verify-image.sh` runs the api container once with `SITE_MODE=coming_soon` and checks the served title.

## 6. Deploy

Task 10's production step deploys the same image with the production variables above, then `scripts/verify-deploy.sh production` (coming-soon mode): health OK with `site_mode: "coming_soon"`, deep 200, the coming-soon title served at `/`, and the sign-up endpoint answering 422 to an invalid address (no row written). The production deploy still requires John's explicit go, and rollback is the dashboard route in `DEPLOY.md`.

## 8. Amendments (2026-09-06, from the Task 11c review — controller rulings, surfaced to John)

1. **Client address for the per-IP limits (§3) — RIGHTMOST `X-Forwarded-For` hop, not the first.** A reverse proxy appends the peer it accepted, so every earlier hop is caller-supplied text; keying on it made the 5/min and 30/day limits bypassable by rotating a header. The rightmost hop is the client as Railway's edge saw it. Proven live on QA before production (Task 11f Step 4b: six requests with different spoofed first hops → the sixth is 429); without the header the peer address is used.
2. **Fail closed.** If Redis or Postgres is unreachable the endpoint answers `503 {"error": "unavailable"}` and stores nothing; failures are logged by exception type only, never with the address (the engine hides bound parameters).
3. **One 422 body.** Every malformed request — missing or non-string `email`, non-object or unparseable JSON — answers `422 {"error": "invalid_email"}`; FastAPI's echoing `detail` envelope is never returned.
4. **Body cap.** Bodies over 4096 bytes answer `413 {"error": "too_large"}` before parsing.
5. **Validation.** NFKC normalisation before trim/lowercase (one human address, one row); ASCII control characters and Unicode bidi controls are rejected (U+0000 is unstorable in Postgres; the rest would be stored verbatim for the Wave-2a pipeline to read).

## 7. Out of scope

Sending any email; favicon and Open Graph assets (John supplies); analytics; any change to the marketplace or to QA.
