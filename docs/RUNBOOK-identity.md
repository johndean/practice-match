# Practice Match — identity, access and email runbook

The operator page for Wave 2a: reviewing applicants, granting roles, minting automation tokens,
reading the audit trail, and the three things that go wrong (an email that never arrived, a member
locked out, a leaked Resend key). Deployment and variables are in [DEPLOY.md](../DEPLOY.md); the
design this implements is
[the identity spec](superpowers/specs/2026-09-05-identity-access-email-design.md).

Every path below is the API. There is no separate admin CLI: the Admin → Users tab in the app calls
exactly these endpoints, and `docs/superpowers/plans/2026-09-05-practice-match-identity-access-email.md`
is the plan they were built from. `tests/test_docs.py::test_identity_runbook_endpoints_exist` walks
`app.main`'s route table against this file, so a path here is a path the server serves.

## 0. Before you start

| | |
|---|---|
| **Host** | QA `https://qa.foundation.vin` · production `https://foundation.vin`. Everything below is rehearsed on QA first. |
| **Who** | `staff` reviews and decides; `admin` also grants roles and mints tokens (`app/auth/permissions.py` is the matrix — `GET /api/admin/permissions` prints the copy the server is actually running). |
| **Re-auth** | Revoke, role grants and token minting need a password confirmation from the last 10 minutes: `POST /api/auth/reauth` with `{"password": "…"}`, then the action. Past `deps.REAUTH_WINDOW` (10 min) the answer is `403 REAUTH_REQUIRED` — re-confirm and repeat. |
| **CSRF** | Every state change made with a session cookie must send `X-CSRF-Token` equal to the `pm_csrf` cookie and an `Origin` of the site, or the answer is `403 CSRF` / `403 ORIGIN`. Bearer (`api_token`) callers send neither. |
| **Tokens** | An `api_token` can never re-authenticate (`403 REAUTH_TOKEN`) and can never manage tokens (`403 TOKEN_SCOPE`), whatever role it carries — so Revoke, grants and minting are always a human with a session. See [DEPLOY.md → Automation tokens](../DEPLOY.md#automation-tokens). |
| **Refusals** | One envelope everywhere: `{"error": {"code": "…", "message": "…"}}`. `401 UNAUTHORIZED` is deliberately identical for a missing and an invalid credential. |

Signing in from a terminal, with a cookie jar the rest of this page reuses:

```bash
H=https://qa.foundation.vin
curl -sS -c /tmp/pm.jar -X POST "$H/api/auth/signin" \
  -H 'Content-Type: application/json' -H "Origin: $H" \
  -d '{"email":"you@example.org","password":"…"}'
CSRF=$(awk '$6=="pm_csrf"{print $7}' /tmp/pm.jar)
curl -sS -b /tmp/pm.jar "$H/api/me"
```

Add `-b /tmp/pm.jar -H "Origin: $H" -H "X-CSRF-Token: $CSRF"` to every `POST` below. Re-read `CSRF`
after any call that re-issues the cookies (sign-in, accept-invite, password change).

## 1. The first admin

`scripts/bootstrap_admin.py` creates (or reactivates) an `active` account with the `admin` grant and
**no usable password**, then prints a single-use 24-hour invite link. There is no default password and
none is ever printed; the link is the only way in, and it lands on `POST /api/auth/accept-invite`.

```bash
ENVIRONMENT=qa poetry run python scripts/bootstrap_admin.py --email person@example.org
```

* On production the script refuses without `--production` (exit 2) — say it out loud, like
  `scripts/deploy.sh`'s Railway guard.
* An address that already exists in `pending`, `needs_review`, `declined`, `suspended` or `revoked`
  is refused with exit 3 unless `--reactivate` is passed: each of those states is a recorded staff
  decision with an audit row behind it.
* Issuing a link retires every unused `invite` token the account already had, so a link printed to a
  terminal or a chat window an hour ago stops working.
* Every run writes an audit row (`admin.bootstrap`, or `admin.bootstrap.refused`).

The link is a credential. Send it to the person over a channel you would send a password reset over,
and never paste it into a shared log.

## 2. The review queue

`GET /api/admin/users` — every account in every state, newest first, the caller's own included.
Query parameters: `state` (any of `unverified`, `verified`, `pending`, `needs_review`, `declined`,
`active`, `suspended`, `revoked`), `kind` (`buyer`/`seller`), `role`, `limit` (capped at 200) and
`cursor` (the previous page's `next_cursor`). Guarded by `users.review`; **not** audited, so polling
the tab leaves no trail.

```bash
curl -sS -b /tmp/pm.jar "$H/api/admin/users?state=pending&limit=50"
```

Each row carries the account, its live `grants` (with who granted each and when) and its newest
application (`application_id`, `kind`, `fields`, `flags`, `application_status`, `submitted_at`).
`flags` are hints only — a `CONSOLIDATOR_KEYWORDS` match is a note for a reviewer, never a decision.

`GET /api/admin/users/{account_id}` — the application detail, with the full answer/decision history.
This read **is** audited (`users.view_detail`): opening somebody's application leaves a row, and that
is deliberate.

## 3. Deciding an application

`POST /api/admin/users/{account_id}/decide` with `{"action": "…", "note": "…"}`.

Every action emails the member except `reinstate` — the Email column names the template, so you can
find the row in `email_outbox` (§8) and know before you click that the person will hear about it.

| Action | From | To | Note | Email | Effect |
|---|---|---|---|---|---|
| `approve` | `pending`, `needs_review` | `active` | optional | `application_approved` (buyer) / `seller_application_approved` | grants the application's `kind` role |
| `decline` | `pending`, `needs_review` | `declined` | **required** | `application_declined` / `seller_application_declined`, carrying your note | — |
| `request_info` | `pending` | `needs_review` | **required** | `application_info_requested` (one template for both kinds) | your note becomes the applicant's `info_request` |
| `suspend` | `active` | `suspended` | **required** | `account_suspended` | ends every session at once |
| `reinstate` | `suspended` | `active` | optional | **none** | — |
| `revoke` | every state but `revoked` | `revoked` | **required** | `account_revoked` | revokes every role grant and ends every session — **needs re-auth** |

* A missing note where one is required is `422 NOTE_REQUIRED`; an action the state does not allow is
  a `409`; an unknown action is `422 BAD_ACTION`.
* Nobody may `suspend` or `revoke` their own account, and a non-`admin` may not act on a `staff` or
  `admin` target.
* Every decision is audited (`users.decide`, or `users.revoke`) with the state before and after and
  your note as the reason. The note is free text a member may eventually read — write it as such.
* `suspend`/`revoke` end sessions immediately; every other decision takes effect within the 60 s
  principal cache at worst.

A seller application is made from an account that is already `active`: approving it adds the
`seller` role and leaves the account's state alone.

## 4. Roles

`POST /api/admin/users/{account_id}/grants` with `{"role": "staff", "grant": true, "reason": "…"}`.
`admin` only, in re-auth, audited with the roles before and after. Roles: `buyer`, `seller`, `staff`,
`admin`.

Two floors under removals: an `admin` grant is never removed from its own holder, and never when it
is the last live one — `roles.grant` is admin-only, so zero admins is a state with no way back short
of `bootstrap_admin.py` and database credentials.

**A removal cascades to automation.** Every live `api_token` that account minted whose role it may no
longer mint is revoked in the same transaction. The ids come back as `revoked_tokens`, and the trail
carries one row per token (`tokens.revoke`, `reason='grant_removed'`). There is no list-tokens
endpoint, so that response and the audit trail are the record — read them when you demote somebody,
and mint replacements from an account that still holds the role.

## 5. Automation tokens

`POST /api/admin/tokens` with `{"name": "k6-qa", "role": "buyer", "days": 90}`. `admin` only, in
re-auth, audited (`tokens.create`, with the role — never the secret).

```bash
curl -sS -b /tmp/pm.jar -H "Origin: $H" -H "X-CSRF-Token: $CSRF" \
  -X POST "$H/api/auth/reauth" -H 'Content-Type: application/json' -d '{"password":"…"}'
curl -sS -b /tmp/pm.jar -H "Origin: $H" -H "X-CSRF-Token: $CSRF" \
  -X POST "$H/api/admin/tokens" -H 'Content-Type: application/json' \
  -d '{"name":"k6-qa","role":"buyer","days":90}'
```

* **Shown once.** The response is `{"token": "pm_<id>.<secret>"}` and only the SHA-256 is stored. A
  token not copied out of that response is gone; mint another.
* Present it as `Authorization: Bearer pm_<id>.<secret>`. No cookie, no CSRF header.
* `days` is clamped into 1..90. The token dies with its minter: suspending or revoking that account
  kills every token it minted, on the next request.
* Nobody mints a token that administers more than they do (`422`/`403` on the attempt).
* `POST /api/admin/tokens/{token_id}/revoke` — audited, `404` if it was already revoked. **Rotate by
  minting the replacement first, switching the consumer's secret, then revoking the old one.**

The token ids you can revoke come from the mint's audit row (`GET /api/admin/audit`, `action` of
`tokens.create`) or from a demotion's `revoked_tokens`.

## 6. The audit trail

`GET /api/admin/audit` — newest first, `limit` default 100, capped at 500. `audit_log` is
append-only by trigger (`migrations/014_audit_log.sql`), so this is the only way to read it short of
psql, and the read itself is deliberately **not** audited.

```bash
curl -sS -b /tmp/pm.jar "$H/api/admin/audit?limit=50"
```

Actions worth knowing by name: `users.view_detail`, `users.decide`, `users.revoke`, `roles.grant`,
`tokens.create`, `tokens.revoke`, `signin.failure_burst` (a fifth failed sign-in on one address in
the window), `signin.refused_state` (correct password on a suspended or revoked account — exactly
what an admin who has just suspended somebody wants to see), `admin.bootstrap`.

Secret-shaped keys are redacted out of `before`/`after`; `reason` is not redacted, which is why it
carries the decision and the reviewer's note and nothing else.

## 7. The applicant's own side

For reproducing a report, and for the paths the account screens call:

* `POST /api/auth/signup` — `{"email": …, "password": …}`, answers `202 {"status": "check_email"}`
  for every address there is. Worth knowing as an operator because it is **also the re-send path
  for a verification link**: while the account is still `unverified`, signing up again re-issues a
  fresh 24 h `verify` token and queues `verify_email` again (I9a fix round 1). It does **not**
  change the password, and from `verified` onward it sends `account_exists` and mints nothing. §8's
  table is where this matters.
* `POST /api/applications` — `{"kind": "buyer"|"seller", "fields": {…}}`, answers `202`. A buyer
  applies from `verified` and the account moves to `pending`. A seller applies from an `active`
  buyer account and the account state does not move. A re-application after a decline is a **new
  row**, not a reused one.
* `POST /api/applications/{application_id}/answer` — `{"answer": "…"}`. The applicant's reply to a
  reviewer's `request_info`, on the same row: it goes back to `pending`, and
  `application_received` is queued again. Only from `needs_review`, only the caller's own row (a
  row that is neither is one indistinguishable `404`).
* `GET /api/applications/me` — `current` (the one open row, or the newest row when nothing is open)
  and `history` behind it, with `info_request`, `decision`, `decision_note`, `decided_at` and
  `fields` (the applicant's own last answers — `_mine_row` in `app/api/applications.py` — which is
  what pre-fills the re-apply form after a decline).
* `GET /api/config` — public, no credential: `{"market_data_public": false}`. The browser reads it
  before `/api/me` on every page load, and `scripts/verify-deploy.sh` probes it. On production the
  boolean must be `false`.

## 8. "I never got the email"

Delivery is an outbox drained by the worker's `mail.send` beat, once a minute. Nothing in the
request path talks to Resend, so a missing email is one of five things — check them in this order.

1. **Is there a row at all?** One per action, in `email_outbox`, keyed by `idempotency_key`:

   ```sql
   SELECT id, to_email, template, status, attempts, last_error, created_at, sent_at, delivered_at
     FROM email_outbox WHERE to_email = 'person@example.org' ORDER BY id DESC LIMIT 20;
   ```

   No row means the action never happened — go back to the audit trail. `status` is one of
   `queued`, `sent`, `suppressed`, `failed`, `bounced`, `complained`.

2. **`status='suppressed'` on QA — the allowlist.** Outside production `EMAIL_ALLOWLIST` is
   fail-closed: an **empty** list delivers to **nobody** and every row is recorded `suppressed`.
   That is what stops a QA sign-up emailing a real person. Add the whole address (not a domain) to
   `EMAIL_ALLOWLIST` on **both** the api and the worker for that environment. A suppressed row is a
   finished row and is **not** retried, so the mail has to be caused again — and how depends on
   which template it was. The same table applies to a row that was genuinely lost (`failed` past
   its attempts, or `sent` to a mailbox that never received it):

   | Template | How to cause it again |
   |---|---|
   | `verify_email` | The person **signs up again on the same address** — `POST /api/auth/signup` — or, if they are already signed in on the unverified account, presses **Send it again** on the "Check your email" card, which is `POST /api/auth/verify/resend` (session-authenticated, `unverified` only, A-S4.1) and needs no password. Either way, while the account is still `unverified` a fresh 24 h `verify` token is issued and `verify_email` queued again (I9a fix round 1), so an expired or suppressed link is never a dead end. Their old link keeps working too, if they still have it. **Three attempts per address per 24 hours** (`limits.SIGNUP_EMAIL`, SHARED by both routes — they count into one bucket keyed on the address): the fourth is refused `429` *before* any mail is queued — so fix the allowlist (or whatever suppressed the row) **before** asking them to try again, or you spend an attempt on a mail that will be suppressed too. The window is a fixed 24 h bucket, not a rolling one, so it clears at the boundary and `Retry-After` reports the whole 24 h as an upper bound rather than the real wait. There is no operator override, and the bucket is keyed on the address, so nothing done on another one shortens it. |
   | `password_reset` | The person uses **Forgot password** — `POST /api/auth/password/forgot` — which always issues a fresh 1 h token and retires the previous one. Works from `verified` and `active` only. |
   | `account_exists` | Nothing to do: it is a notice to the address's owner that somebody tried to sign up as them, not something they act on. |
   | `application_received`, `application_info_requested` | The applicant re-submits: `POST /api/applications/{application_id}/answer` from `needs_review`, or a fresh `POST /api/applications` after a decline. |
   | `application_approved`, `application_declined`, `seller_*`, `account_suspended`, `account_revoked` | **The decision cannot be repeated** — the state machine refuses a second decision from `active`/`declined`/`revoked`, and re-deciding would write a second audit row for one decision. Tell the person directly, and use the audit trail (§6) as the record of what was decided and when. |
   | `password_changed`, `signin_new_device` | Notices of something that already happened; there is nothing to re-send. |

   Only the first two rows are self-service. If you are tempted to reach into `email_outbox` and set
   a row back to `queued`, don't: the sender claims rows by `status='queued'` and the row's
   `idempotency_key` is what stops a double delivery, so hand-editing status is how one person gets
   two links.

3. **`status='bounced'` or `'complained'` — the suppression list.** Resend's webhook
   (`POST /api/webhooks/resend`) writes both the row status and an `email_suppression` entry:

   ```sql
   SELECT email, reason, at FROM email_suppression WHERE email = 'person@example.org';
   ```

   A hard bounce usually means the address is wrong — correct it with the member and re-do the
   action. Remove a suppression row only when you know why it was written (`reason='manual'` is for
   entries an operator added deliberately).

4. **`status='queued'` and old — the worker.** `sent_at IS NULL` with a growing `attempts` and a
   `last_error` is a send that is failing; `attempts=0` and nothing moving means the beat is not
   running or `RESEND_API_KEY` is unset on the worker (it raises on every beat rather than leaving
   mail silently queued). `railway logs --service worker --environment <env> --lines 50` — look for
   `celery@… ready` and the `mail.send` beat.

5. **`status='sent'` but `delivered_at IS NULL`.** We handed it to Resend and the recipient's mail
   server has not accepted it (or the webhook is not wired). Check the Resend dashboard for that
   `provider_id`, and check `RESEND_WEBHOOK_SECRET` is set on the api — unset, the webhook answers
   `401` to every call rather than trusting one.

The app serves five account routes: `/signup` and `/forgot` (no token) and `/verify`, `/reset`,
`/accept-invite` (each reads a `?token=` from the query string once and never writes one back into
the address bar). The links inside verify and reset mail, and the invite link
`scripts/bootstrap_admin.py` prints (§1 — it is handed over directly, never queued as mail), all
point at `LINK_BASE_URL` plus one of those three: `/verify?token=…`, `/reset?token=…`,
`/accept-invite?token=…`. A wrong `LINK_BASE_URL` value sends people to the other environment,
which looks exactly like "the link doesn't work".

## 9. A locked-out member

Sign-in counts **failures only** (`app/auth/limits.py`), so a busy day cannot lock anyone out:

| Bucket | Limit | Window |
|---|---|---|
| failures per address (`SIGNIN_EMAIL`) | 10 | 15 min |
| requests per client IP (`SIGNIN_IP`) | 30 | 15 min |
| sign-ups per IP / per address | 5 / 3 | 1 h / 24 h |
| password-reset requests per address / per IP (`FORGOT_EMAIL`, `FORGOT_IP`) | 3 / 10 | 1 h |
| verify + reset token attempts per IP (`TOKEN_IP`) | 30 | 1 h |

* A successful sign-in clears the address's failure count. **A lockout therefore expires on its
  own, within 15 minutes** — that is the answer nine times in ten, and there is no unlock endpoint.
* A fifth failure writes `signin.failure_burst` to the audit trail. Several of those against one
  address from different IPs is worth a look; one is somebody's caps lock.
* Both refusals answer `429` with `Retry-After` set to the whole window (an upper bound — the bucket
  rolls over sooner).
* **A correct password that still fails** is the interesting case: `suspended` and `revoked`
  accounts get the same generic `401` as a wrong password, and write `signin.refused_state`. Check
  the audit trail and the account's state before believing a password report.
* The member's own remedy is `POST /api/auth/password/forgot` (which answers `202` whether or not
  the address exists). `POST /api/auth/signout-all` ends every session of the caller's account.

Never "reset" a member by editing `account` in psql. Use the endpoints — they are the things that
leave a trail.

## 10. Rotating `RESEND_API_KEY`

The key lives only on the **worker**, per environment, and never in git, chat or a CI log — the same
rule as `CENSUS_API_KEY`. Rotate it whenever it may have been seen, and after anyone with access
leaves.

1. `railway status` → must print **Project: Practice Match**.
2. Create the new key in the Resend dashboard. Do not delete the old one yet.
3. `railway variable set RESEND_API_KEY=<new> --service worker --environment <env>` — QA first.
4. Watch the worker come back and drain the outbox: `railway logs --service worker --environment <env> --lines 50`,
   then check that a `queued` row reaches `sent` within a couple of minutes (§8's query).
5. Repeat for production, then **revoke the old key in the Resend dashboard.**
6. If step 4 shows sends failing, put the old key back (it still works until step 5) and
   investigate; queued mail is not lost, it is retried.

`RESEND_WEBHOOK_SECRET` (api only) rotates the same way, from the endpoint's page in the dashboard.
While it is mismatched the webhook answers `401`, so bounces are not recorded — re-check
`email_suppression` after the swap.

## 11. Test and QA accounts

`scripts/seed_persona.py` seeds the ten accounts the visual suite and a QA click-through need — three
members (`buyer@`, `seller@`, `design@practice-match.test`, all "Dr. Rachel Mendes of the StartUp
Club", differing only in grants), three applicants (`pending@`, `needs-review@`,
`declined@practice-match.test`, one per gate state — only `needs-review@` and `declined@` carry a
real application row; `pending@` has none) and four identity-screen accounts (`unverified@`,
`verify-me@`, `verified@`, `invited@practice-match.test`) covering the two states the
sign-up/verify/forgot/reset/accept-invite screens start from (`unverified@` and `verify-me@` are
both `unverified`; `verified@` and `invited@` are both `verified`). `verify-me@` exists solely to own
the twelve `verify` fixture tokens, so consuming one during a test never confirms the `unverified@`
account the check-email/resend states need to stay unverified. Idempotent; run it as often as you
like.

```bash
PERSONA_PASSWORD=… ENVIRONMENT=qa poetry run python scripts/seed_persona.py
```

* It **refuses on production, with no override flag** (exit 2). A fixture account holding `admin` on
  the stakeholders' real data is not something a `--yes` should be able to buy.
* `PERSONA_PASSWORD` is held in the operator's macOS Keychain (service `practice-match-qa`, account
  `PERSONA_PASSWORD`; read with `security find-generic-password -a PERSONA_PASSWORD -s
  practice-match-qa -w` into a subprocess environment, never printed); read by no service; passed to
  the seed and the harness through the shell; never on production (A-S6.2, superseding A-S6.1) —
  `scripts/seed_persona.py` and the Playwright harness read it from the shell they are
  given, never Railway directly. Unset, the script falls back to its own documented default
  (`scripts/seed_persona.py`'s `DEFAULT_PASSWORD`), which is also the Playwright harness's default
  and is pinned equal to it by
  `tests/test_docs.py::test_the_playwright_persona_password_default_matches_seed_persona`.
* The addresses are all `.test` (RFC 6761): never deliverable, by design. They are also why the QA
  `EMAIL_ALLOWLIST` can stay empty.
* `seller@practice-match.test` also OWNS the eighteen demo hospitals on QA (spec 2026-09-08 D25), so
  run this script BEFORE `scripts/seed_listings.py`: the owner is looked up by address at seed time,
  and if the account is missing the hospitals are simply seeded unowned. A hospital the seller then
  edits becomes their own for good (amendment A-SL21) and later imports skip it. DEPLOY.md's
  "Seeding the demo hospitals (QA)" has the rest.
* These are not a way in for a real reviewer. Real people get `scripts/bootstrap_admin.py` (§1) and
  a grant (§4).

## 12. QA parity run

Any Playwright invocation pointed at a live `PW_APP_URL` — smoke, sign-in, the account flows,
whichever project — reseeds QA's fixtures automatically, before the first test AND after the last
(`frontend/tests/global-setup.ts` / `global-teardown.ts`, Task S7): the run needs no manual seed
step and cannot leave QA's fixtures mutated for whoever opens it next.

**The remote run is smoke, sign-in and the account flows from here (A-L6.2).** `visual.spec.ts`
and `dom.spec.ts` skip themselves whenever `PW_APP_URL` is set, because they compare the app
against baselines generated from the design file and QA now serves its practices from the seeded
`listing` table — eighteen real hospitals where the design has twenty-one fixtures — so every
Browse, detail, mobile and market state would differ by construction rather than by regression.
Those two oracles are proved locally instead, where `prepare()` answers `/api/listings` with the
design's own fixtures (spec D6); the command below is unchanged and simply runs the specs that
can still mean something remotely.

```bash
railway status                                                                       # must print: Project: Practice Match
railway variable list --service api --environment QA --json > /tmp/pm-qa-vars.json   # names AND values — never cat this file
cd frontend
env $(python3 -c 'import json; d = json.load(open("/tmp/pm-qa-vars.json")); print(" ".join(f"{k}={d[k]}" for k in ("DATABASE_URL","API_SECRET_KEY","ENVIRONMENT","REDIS_URL")))') \
    PERSONA_PASSWORD="$(security find-generic-password -a PERSONA_PASSWORD -s practice-match-qa -w)" \
    PW_APP_URL=https://qa.foundation.vin npx playwright test --config=tests/playwright.config.ts --project=app
rm -f /tmp/pm-qa-vars.json
```

`npm run test:e2e` is the same command (`frontend/package.json`'s script already carries
`--config=tests/playwright.config.ts --project=app`; `frontend/tests/playwright.config.ts` is the
only config in the repo), with `PW_APP_URL` and the five variables set ahead of it instead.

* The reseed needs exactly five variables — `DATABASE_URL`, `PERSONA_PASSWORD`, `API_SECRET_KEY`,
  `ENVIRONMENT`, `REDIS_URL`; a refusal names whichever of the five is missing. Four are pulled from
  Railway in the one JSON read above and handed straight into the subprocess environment; never
  print that file, and delete it when you are done. `PERSONA_PASSWORD` is held in the operator's
  macOS Keychain (service `practice-match-qa`, account `PERSONA_PASSWORD`; read with
  `security find-generic-password -a PERSONA_PASSWORD -s practice-match-qa -w` into a subprocess
  environment, never printed); read by no service; passed to the seed and the harness through the
  shell; never on production (A-S6.2, superseding A-S6.1) — the other four are real `Settings`
  fields the api and worker also read.
* On a refusal — a host outside `qa.foundation.vin`/`localhost`/`127.0.0.1`, or
  `ENVIRONMENT=production` — the planner prints `remote reseed refuses this target:
  <host>/<ENVIRONMENT> — only QA and local test hosts may be reseeded`
  (`frontend/tests/global-setup.ts`) and the run never starts. When it DOES run, the seed itself
  prints the target database name and host, never the DSN (`[seed_persona] target database <db> on
  <host>`, `scripts/seed_persona.py`).
* QA's real sign-in rate limit stays real: fifteen of `SIGNIN_IP`'s thirty sign-ins per FIXED
  fifteen-minute window are enough for one full parity run (`frontend/tests/harness.ts`'s traced
  budget: 7 + 2 + 4 + 1 + 1), so budget **one run per window**. A `429` mid-run means wait for the
  quarter-hour boundary and re-run — never loosen the limit to make it pass.
* Only **one remote run at a time**: the fixture restoration is unconditional and the throwaway
  `e2e-…@example.org` sweep is global, so a second run started before the first finishes races the
  same fixtures and addresses.
* The smoke suite's first-map-paint gate budgets 3 s against a remote target (1.5 s locally,
  `frontend/tests/harness.ts`'s `firstMapPaintBudgetMs`) — a run from far from the target region
  carries real network round trips and tile fetches the local budget never measured.

## 13. The launch email

The Coming Soon page collects one thing: an address, and a promise — *"One message, when it
launches. Nothing else, and never shared."* This is how that message is sent, once.

**Before the flip.** Production runs `SITE_MODE=coming_soon` until launch, and controller amendment
A-I5d.5 (John's ruling, 2026-09-09) gates the WHOLE Admin Launch Sign-ups router behind
`SITE_MODE=app` — `GET /api/admin/signups`, `GET /api/admin/signups.csv` and
`POST /api/admin/signups/launch-mail` alike answer `404` before the flip, even to the legacy
`API_SECRET_KEY` operator bearer (this supersedes D-I5d-5, which had mounted the router
unconditionally so the list stayed readable before launch). To read the sign-ups before then, query
the database directly — the same `DATABASE_URL`-from-Railway pattern as §12's QA parity run and
`DEPLOY.md`'s seeding recipe: pull the PostGIS service's `DATABASE_URL` into an env prefix so it
never appears in argv and is never echoed, and run a python one-liner (reading it from its own
process environment, never a command-line argument) that answers the row listing and the same count
the dry run would have:

```bash
railway status                                                                                     # MUST print Project: Practice Match
DATABASE_URL="$(railway variable list --service PostGIS --environment production --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["DATABASE_URL"])')" \
  poetry run python3 -c '
import os
import psycopg2
conn = psycopg2.connect(os.environ["DATABASE_URL"])
with conn, conn.cursor() as cur:
    cur.execute("SELECT email, created_at FROM interest_signup ORDER BY created_at")
    for row in cur.fetchall():
        print(row)
    cur.execute("SELECT count(*) FILTER (WHERE launch_mailed_at IS NULL) AS not_mailed, count(*) FROM interest_signup")
    print(cur.fetchone())
'
```

**Once `SITE_MODE=app`.** `GET /api/admin/signups` reads the list (staff or admin) and
`GET /api/admin/signups.csv` downloads it — capped at `MAX_EXPORT = 100 000` rows
(`app/api/admin_signups.py`); above that it truncates silently, so check the row count against
`not_mailed` from the dry run below before treating a download as the whole list.
`POST /api/admin/signups/launch-mail` with `{"dry_run": true}` answers with the counts and queues
nothing — it writes one audit row, `reason: dry_run`, and nothing else. A real send is additionally
refused with `409 NOT_LAUNCHED` if `SITE_MODE` somehow still reads `coming_soon` at that point — a
defence-in-depth check inside the handler itself, kept even though the router is absent before
then, because the message the mail carries says Practice Match is open.

**Two more gates, ahead of that one (controller amendment A-I5d.4, John, 2026-09-08).** A real send
is refused, in this order, before `SITE_MODE` is even checked:

1. `409 LAUNCH_COPY_NOT_APPROVED` while `app.mail.templates.LAUNCH_COPY_APPROVED` is `False`. John's
   ruling: *"Launch email — COPY NOT YET APPROVED. Do not send."* The proposed subject and body sit
   in that module, marked `>>> COPY FOR JOHN'S APPROVAL <<<`, for him to read and edit; flipping the
   constant is his call, not an operator's, and is made in the same commit that pins the approved
   text verbatim.
2. `409 LAUNCH_MAIL_NOT_CONFIGURED` while `VIN_FOUNDATION_POSTAL_ADDRESS` is unset. The mail's
   CAN-SPAM footer prints `VIN Foundation · {address}`, and John's ruling was explicit — *"Do not
   invent the address"* — so an unset setting refuses the send by name rather than shipping a
   footer with a blank line. Set it in Railway (api **and** worker) once the VIN Foundation's
   official postal address is known.

A dry run is exempt from all three refusals — reading the counts is always safe, whatever state the
copy or the address is in; only an actual send is gated.

**The order at launch.**
1. Set production `SITE_MODE=app` in Railway (after `railway status` prints **Project: Practice
   Match**) and `scripts/deploy.sh production`; `scripts/verify-deploy.sh production` must report
   `site_mode: "app"`.
2. Sign in as an admin and confirm your password (`POST /api/auth/reauth`) — `signups.notify` is a
   re-authenticated action and no api token can ever satisfy it (the legacy `API_SECRET_KEY`
   operator bearer is the one exemption to the re-auth gate, until Task I9 removes it — the copy
   and address gates above still bind it, so it cannot skip either refusal).
3. `POST /api/admin/signups/launch-mail` with `{"dry_run": true}`. Read `not_mailed`. That is how
   many people are about to hear from the VIN Foundation.
4. `POST /api/admin/signups/launch-mail` with `{"dry_run": false}`. It queues at most 500 per call
   and answers with `remaining`; repeat until `remaining` is 0.
5. Watch the outbox drain. The worker's `mail.send` runs every minute and takes 25 rows a batch, so
   a list of 1,500 takes about an hour. Nothing is lost if the worker restarts: a claimed row's
   lease expires and it is picked up again, and the provider's idempotency key stops that becoming
   a second delivery.

**The address is frozen at queue time.** Each `email_outbox` row carries the `postal_address` that
was configured when it was queued — the worker renders `email_outbox.params`, never the current
`VIN_FOUNDATION_POSTAL_ADDRESS` setting. Fixing the Railway variable after a batch has already been
queued does **not** fix those rows. To correct a wrong address caught before the worker has sent
the batch (`status = 'queued'`; a `sent` row cannot be recalled). **Stop the mail worker first** (scale the
`worker` service to zero or pause `mail.send`): a row the worker has already claimed still reads `status = 'queued'`
until `mark()` runs, so deleting while the worker drains can double-mail up to one batch — the three statements below
also carry `AND next_attempt_at <= now()` so an in-flight claim is never touched:

```sql
-- 1. See which sign-ups this batch would affect (the idempotency key is "<signup id>:launch_announcement:1").
SELECT id, to_email, split_part(idempotency_key, ':', 1) AS signup_id
  FROM email_outbox WHERE template = 'launch_announcement' AND status = 'queued' AND next_attempt_at <= now();
-- 2. Clear launch_mailed_at for exactly those sign-ups, so the next real send picks them up again.
UPDATE interest_signup SET launch_mailed_at = NULL
 WHERE id::text IN (SELECT split_part(idempotency_key, ':', 1)
                       FROM email_outbox WHERE template = 'launch_announcement' AND status = 'queued' AND next_attempt_at <= now());
-- 3. Delete the wrong-address rows — the worker has not sent them, so nothing already went out.
DELETE FROM email_outbox WHERE template = 'launch_announcement' AND status = 'queued' AND next_attempt_at <= now();
```

Then correct `VIN_FOUNDATION_POSTAL_ADDRESS` in Railway and repeat step 4 of the order above.

**Sending it twice is safe.** Each sign-up carries `launch_mailed_at`; a row that has it is never
selected again. A person who signs up after the send is picked up by the next call and gets the
same message — which is right: they were promised it too.

**On QA nothing leaves.** `EMAIL_ALLOWLIST` is fail-closed outside production: an address that is
not on it is recorded `suppressed` with the reason, and an empty allowlist sends to nobody. A QA
rehearsal therefore still stamps `launch_mailed_at`, so rehearse on QA data, never against a copy
of the production list.
