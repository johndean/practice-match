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
  and `history` behind it, with `info_request`, `decision`, `decision_note` and `decided_at`.
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
   | `verify_email` | The person **signs up again on the same address** — `POST /api/auth/signup`. While the account is still `unverified` that re-issues a fresh 24 h `verify` token and queues `verify_email` again (I9a fix round 1), so an expired or suppressed link is never a dead end. Their old link keeps working too, if they still have it. |
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

The links inside verify and reset mail point at `LINK_BASE_URL`. A wrong value sends people to the
other environment, which looks exactly like "the link doesn't work".

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

`scripts/seed_persona.py` seeds the six accounts the visual suite and a QA click-through need — three
members (`buyer@`, `seller@`, `design@practice-match.test`, all "Dr. Rachel Mendes of the StartUp
Club", differing only in grants) and three applicants (`pending@`, `needs-review@`,
`declined@practice-match.test`), one per gate state. Idempotent; run it as often as you like.

```bash
PERSONA_PASSWORD=… ENVIRONMENT=qa poetry run python scripts/seed_persona.py
```

* It **refuses on production, with no override flag** (exit 2). A fixture account holding `admin` on
  the stakeholders' real data is not something a `--yes` should be able to buy.
* `PERSONA_PASSWORD` is read from the shell only — never a Railway variable, nothing in the api or
  worker reads it. Unset, the script uses its documented default (`.env.example`), which is also the
  Playwright harness's default and is pinned equal to it by
  `tests/test_docs.py::test_the_playwright_persona_password_default_matches_seed_persona`.
* The addresses are all `.test` (RFC 6761): never deliverable, by design. They are also why the QA
  `EMAIL_ALLOWLIST` can stay empty.
* These are not a way in for a real reviewer. Real people get `scripts/bootstrap_admin.py` (§1) and
  a grant (§4).
