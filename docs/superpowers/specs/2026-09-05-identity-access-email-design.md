# Practice Match — Identity, Access and Email (Wave 2a of Sub-project 2) — Design

**Date:** 2026-09-05 · **Status:** approved in brainstorming (Sections A–E, Section A red-teamed for security, performance and zero-regression) · **Depends on:** Platform spec/plan (SP1), Quality and Performance Policy, Census plan A9 (operator token it replaces), Map-engines spec (CSRF, `registry_change_log`, engine activation). **Followed by:** Wave 2b — Listings and Requests (own spec), which consumes the `seller`, `listing.*` and `request.*` permissions defined here.

## 0. Decisions taken in brainstorming

| Question | Decision |
|---|---|
| Waves | **2a Identity, Access and Email now; 2b Listings and Requests next.** 2a unblocks the Map-engines Admin switch and the live Data Sources tab. |
| Sign-in | **Own email + password only; SSO (Flowint) later.** Members register with **any email address** — the domain is never restricted or inferred from VIN membership. The design's "VIN username" copy changes to "Email" (design delta). |
| Roles | **Separate Buyer and Seller roles**, plus Staff and Admin. Seller is obtained through a **seller application reviewed by staff**. |
| Second factor | **Passwords only for now**, with the compensating controls in §3 and §4; MFA is one migration away and flagged for the VIN Foundation before the first production admin exists. |
| Email | **Verify first, then apply.** Sender `no-reply@foundation.vin` through Resend; `foundation.vin` is only the sender domain. |
| Permission matrix | **Code-defined, exhaustively tested, read-only in Admin** (a Permissions tab). |
| Sessions | **Server-side sessions + httpOnly cookie**; revocation takes effect on the member's next request. |

## 1. Scope

**In:** account creation and email verification; the buyer application (the design's fields) and the seller application; staff decisions (Approve · Decline · Request info · Suspend · Revoke); roles and grants; server-side sessions, CSRF/Origin, password policy, reset, lockout, rate limits, security headers; the permission matrix and its three enforcement layers; `api_token`s for automation; the audit log; the Resend pipeline (outbox, worker, webhook, QA allowlist, templates); the Admin Users tab live and a read-only Permissions tab; wiring the prototype's sign-in/apply to the API and executing the launch-removal list; replacing the operator token everywhere.

**Out:** listings, the seller wizard, requests/messaging, document locks, Admin Listings/Requests tabs (Wave 2b); SSO; MFA (designed for, not built); payments.

## 2. Accounts, states, roles

**Lifecycle.** Sign up (email + password) → verify (24 h link) → application → `pending` → staff decision: Approve (→ `active`, Buyer granted), Decline (→ `declined`), Request info (→ `needs_review`) → optional seller application → Approve/Decline (Seller granted). Suspend (reversible) and Revoke (terminal) act on the account and override every role on the next request. Staff and Admin are granted by an admin; never applied for. The first admin is created by `scripts/bootstrap_admin.py`, which issues a one-time invite link to an address John supplies (no default password; audited).

**Lifecycle — amended 2026-09-07 (John: the applicant's path back must exist — "YES").** `needs_review` → the applicant answers the reviewer's question **in the app** and re-submits → `pending` (the answer and `resubmitted_at` are stored on the same application row; staff see them with the history). `declined` → the applicant may **re-apply** → a new application row, `pending`, with the earlier rows kept as history; at most one open (`pending`/`needs_review`) application per account. Both paths are audited (`applications.answer`, `applications.reapply`) and re-send `application_received` (a new idempotency cause). The API lands in Wave 2a Task I5c; the applicant-facing screens (an answer field on the info-requested gate state, a Re-apply action on the declined gate state) are **absent from the V2/V3 designs** and need a Rev 3 design from John before I8 wires them — until then staff act on e-mail replies as the design's own copy says.

**Two orthogonal facts.** `account.state ∈ {unverified, verified, pending, needs_review, declined, active, suspended, revoked}` and `role_grant(role ∈ {buyer, seller, staff, admin})`. Effective permissions = union of active grants **only while `state = active`**; every other state sees the gate screens.

**Tables (migrations `010`–`015` — amended 2026-09-07: the reserved range used to end at `019`, which overlaps Census SP3-A's `017`–`059`):**

| Table | Columns (essentials) |
|---|---|
| `account` | `id uuid`, `email citext unique` (lower-cased, any domain), `password_hash` (Argon2id), `state`, `display_name`, `affiliation_label` (free text, e.g. "StartUp Club"), `created_at`, `last_sign_in_at` |
| `application` | `id`, `account_id`, `kind ∈ {buyer, seller}`, `fields jsonb` (buyer: `name, vin_member_id?, school_year, license_state, employer, intent, affirm`; seller: `practice_name, ownership_attestation, license_state`), `flags text[]` (reviewer hints: `disposable_domain`, `employer_keyword`), `submitted_at`, `status`, `decided_by`, `decided_at`, `decision_note`, `info_request` |
| `role_grant` | `account_id`, `role`, `granted_by`, `granted_at`, `revoked_at`; unique `(account_id, role) WHERE revoked_at IS NULL` |
| `session` | `id_hash` (SHA-256 of a 256-bit random id), `account_id`, `created_at`, `last_seen_at` (written ≤ once per 5 min), `expires_at`, `reauth_at`, `ip inet`, `user_agent`, `revoked_at` |
| `email_token` | `id`, `account_id`, `purpose ∈ {verify, reset}`, `token_hash`, `expires_at`, `used_at` |
| `api_token` | `id`, `name`, `role`, `token_hash`, `created_by`, `created_at`, `expires_at` (≤ 90 d), `revoked_at`, `last_used_at` |
| `email_outbox` | `id`, `to`, `template`, `params jsonb`, `idempotency_key unique`, `status ∈ {queued, sent, suppressed, failed, bounced, complained}`, `provider_id`, `attempts`, `last_error`, `created_at`, `sent_at` |
| `email_suppression` | `email`, `reason ∈ {bounce, complaint, manual}`, `at` |
| `audit_log` | `id`, `at`, `request_id`, `actor_id`, `actor_role`, `action`, `target_type`, `target_id`, `before jsonb`, `after jsonb` (never hashes or tokens), `ip`, `ua`, `reason`; append-only for the application role |

Retention: declined applications and their PII purged 12 months after decision (VIN Foundation to confirm); expired sessions purged nightly; audit retention an open item.

## 3. Authentication mechanics

| Endpoint | Auth | Behaviour |
|---|---|---|
| `POST /api/auth/signup {email, password}` | none | Creates `account(unverified)` or, for an existing email, performs equal work and returns the same `202`; queues `verify_email` (24 h). Limits 5/h/IP, 3/day/email. |
| `POST /api/auth/verify {token}` | none | Single-use; `unverified → verified`. The `/verify` page POSTs the token from its URL and replaces history. |
| `POST /api/auth/signin {email, password}` | none | Argon2id in a worker thread; success → new session id, cookies `pm_session` (`HttpOnly; Secure; SameSite=Lax; Path=/`) and `pm_csrf` (readable, 128-bit); failure → generic `401` after equal hash work. Lockout 10 failures/email/15 min and 30/IP/15 min → `429` + `Retry-After`. Suspended/revoked accounts receive the generic `401` and an audit row. |
| `POST /api/auth/signout` · `/signout-all` | session + CSRF | Revoke current / all sessions; cache busted. |
| `POST /api/auth/password/forgot {email}` | none | Always `202`; queues `password_reset` (1 h) for `verified+` accounts only. Limit 3/h/email. |
| `POST /api/auth/password/reset {token, password}` | none | Single-use; sets hash; revokes all sessions; audit. |
| `POST /api/auth/password/change {current, new}` | session + CSRF + re-auth | Rotates session id; revokes other sessions. |
| `POST /api/auth/reauth {password}` | session + CSRF | Sets `session.reauth_at`; destructive actions need it within 10 minutes. |
| `GET /api/me` | session or api token | `{ id, email, name, role, initials, state, roles[], affiliation_label }` — `role` is the design's label ("Approved buyer · StartUp Club") computed from grants + `affiliation_label`. |

**Passwords.** ≥ 12 chars (≥ 14 for staff/admin), ≤ 256, any characters; strength score ≥ 3 (zxcvbn-style) checked client- and server-side; screened against HIBP by k-anonymity (5-char SHA-1 prefix; on API failure use the bundled top-100k list and log). Argon2id `m=64 MiB, t=3, p=1`, rehash on parameter change at next sign-in. Nothing about a password is ever logged beyond "changed".

**Sessions.** Server-side rows; idle 14 d, absolute 30 d; new id on sign-in and on every privilege or state change; resolution per request through Redis `session:{hash}` → `{account_id, state, roles, reauth_at}` (TTL 60 s) that is **deleted** on sign-out, password change, any state change or grant change — revocation is effective on the next request (tested). `last_seen_at` written at most every 5 minutes; nightly purge (beat).

**CSRF and origin.** POST/PATCH/DELETE from a cookie session require `X-CSRF-Token == pm_csrf` **and** an `Origin`/`Referer` on the site's host; bearer `api_token` callers are exempt. No endpoint changes state on GET (router-walk test).

**Automation tokens (amended 2026-09-07 — John: "Admin and Staff must be handled in Wave 2a"; tokens "must include Staff/Admin tokens").** `api_token` created by an admin (`tokens.manage`) for a named purpose (`k6-qa`, `e2e-qa`, `deploy-verify`), carrying **any one of the four roles — `buyer`, `seller`, `staff` or `admin`**; the minter must hold the role being granted (no escalation), the creation is a re-authenticated, audited action (`tokens.create` records the role), hashed at rest, ≤ 90 days, revocable; `Authorization: Bearer pm_<id>.<secret>`. A token principal holds its role's permissions with two exceptions, because a token has no session to re-authenticate: it never satisfies a re-auth gate (Revoke, licence decisions, engine activation, role grants, token creation) and it never holds `tokens.manage` — a leaked admin token cannot mint tokens or revoke people. They replace `API_SECRET_KEY`/`auth_stub.py`, which are deleted once CI secrets are switched (one-release overlap in which `require(perm)` accepts either).

**Rate limits.** Redis fixed windows keyed by (route, email) and (route, first `X-Forwarded-For` hop as set by Railway's proxy); constants in `app/auth/limits.py`; responses carry `Retry-After`.

**Headers on every response.** `Strict-Transport-Security: max-age=31536000; includeSubDomains`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, plus the Map-engines per-page CSP on the shell.

**Compensating controls for passwords-only (staff/admin):** the 14-char floor, HIBP screening, **re-authentication before Revoke, licence decisions, engine activation and role grants**, `signin_new_device` email on a new IP/user agent, admin "sign out everywhere", lockout, audit. MFA (TOTP) is designed as an additive `mfa_secret` migration and a `require_mfa` step in `signin`; not built in 2a.

## 4. Permission matrix

Roles: `anonymous · applicant · buyer · seller · staff · admin`. `anonymous` gains `market.read` only while `MARKET_DATA_PUBLIC=true` (replaces the Census plan's bypass with the same behaviour). Source of truth: `app/auth/permissions.py`; generated twin `frontend/src/auth/permissions.ts` (CI diff-checks it).

| Permission | Unlocks | anon | applicant | buyer | seller | staff | admin |
|---|---|---|---|---|---|---|---|
| `page.gate` | `/` sign-in, apply, pending, declined | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `account.self` | `/api/me`, password change, sign-out, own application status | — | ✅ | ✅ | ✅ | ✅ | ✅ |
| `page.browse` · `listing.read` | `/browse?tab=listings`, `/practices/:id` (published; documents per seller unlock — 2b) | — | — | ✅ | ✅ | ✅ | ✅ |
| `market.read` | `/browse?tab=market`, `/api/layers`, `/api/markets*`, `/api/listings/{id}/market`, `/api/map-config` | flag | — | ✅ | ✅ | ✅ | ✅ |
| `layer.google_live` | Google live layers + `/api/listings/{id}/competition/live` (∧ licence ∧ engine) | — | — | ✅ | ✅ | ✅ | ✅ |
| `layer.satellite` | satellite toggle (∧ cleared imagery/engine row) | — | — | ✅ | ✅ | ✅ | ✅ |
| `request.create` · `request.read_own` | `/requests`; express interest; own threads (2b) | — | — | ✅ | ✅ | — | — |
| `seller.apply` | file the seller application | — | — | ✅ | — | — | — |
| `page.seller` · `listing.manage_own` · `request.answer_own` | `/seller`, wizard, own listings, answer own requests (2b) | — | — | — | ✅ | — | — |
| `page.admin` · `users.review` · `users.view_detail` | `/admin?tab=users`; list applications/members (`users.review`, not audited); **view an application's detail** (`users.view_detail`, audited — split 2026-09-08 after the I5 review so that polling the list does not write an audit row per call) | — | — | — | — | ✅ | ✅ |
| `users.decide` | Approve · Decline · Request info · Suspend · Revoke (re-auth for Revoke) | — | — | — | — | ✅ | ✅ |
| `listing.review` · `listing.publish` | `/admin?tab=listings`; publish/unpublish/flag (2b) | — | — | — | — | ✅ | ✅ |
| `request.oversee` | `/admin?tab=activity`; request metadata only | — | — | — | — | ✅ | ✅ |
| `abuse.investigate` | read message contents; every read audited (2b) | — | — | — | — | — | ✅ |
| `data_sources.read` | `/admin?tab=data`, `GET /api/admin/data-sources`, `/changes` | — | — | — | — | ✅ | ✅ |
| `licence.decide` · `engine.activate` | `POST …/license`, `POST …/activate` (re-auth) | — | — | — | — | — | ✅ |
| `roles.grant` | grant/revoke staff, admin; grant seller outside an application (re-auth) | — | — | — | — | — | ✅ |
| `tokens.manage` | create/revoke `api_token`s | — | — | — | — | — | ✅ |
| `audit.read` · `permissions.read` | `/admin?tab=permissions`, `GET /api/admin/audit`, `GET /api/admin/permissions` | — | — | — | — | ✅ | ✅ |

**Scope predicates** ride with `*_own` permissions (`listing.seller_id = me`, `request.buyer_id = me`) and live in the same module; `users.review` never returns hashes; `abuse.investigate` is the only path to message bodies.

**Enforcement.** (1) API: every route declares `Depends(require("perm"))`; `require` resolves session/api token → checks `state = active` → checks the permission → applies re-auth where marked → writes the audit row for audited permissions; undeclared routes fail a test unless in `PUBLIC_ROUTES`. (2) Router: Platform Task 2's `guard()` reads route→permission from `permissions.ts`; a missing permission renders the gate (signed out) or the design's "not available to your account" state (signed in), URL kept. (3) UI: nav items, admin tabs, actions and layer toggles render only with `can(perm)`; layers `enabled = licence ∧ engine ∧ permission`.

**Visual-gate persona.** The visual suite signs in as a seeded **design persona** holding buyer + seller + staff + admin so every design state stays reachable and pixel-identical; per-role hiding is proved by unit and API tests.

**Exhaustive tests.** (a) every route has a permission or is public; (b) every permission is used by ≥ 1 route/page/feature; (c) generated parametrised test: every protected endpoint × every role → 200/403 exactly per the table; (d) the TS twin regenerated and diffed in CI; (e) every Admin action label maps to a permission; (f) row filters tested with owner and non-owner.

## 5. Email through Resend

**Sender/domain.** `no-reply@foundation.vin` ("VIN Foundation — Practice Match"); `Reply-To` a monitored VIN Foundation mailbox (open item). Resend domain verification: DKIM CNAMEs, SPF TXT, DMARC TXT on `foundation.vin` — records handed to John for name.com. Production sends only after Resend reports the domain verified.

**QA safety.** `EMAIL_ALLOWLIST` on QA: only listed addresses are sent; others become `suppressed` outbox rows visible in Admin. Link bases are environment-specific (`qa.foundation.vin` vs `foundation.vin`).

**Templates** (text + HTML, escaped, no tracking pixels, no tokens in subjects): `verify_email` (24 h), `application_received`, `application_approved`, `application_declined`, `application_info_requested`, `seller_application_received/approved/declined`, `password_reset` (1 h), `password_changed`, `signin_new_device` (staff/admin), `account_suspended`, `account_revoked`. Copy follows the design's pending/declined screens.

**Pipeline.** Endpoint writes `email_outbox(queued, idempotency_key = "{account_id}:{template}:{cause_id}")` — never a network call on the request path → Celery `mail.send` (existing worker) → Resend `POST /emails` with the idempotency header → `sent` + `provider_id`; retries at 1 min, 10 min, 1 h, 6 h, then `failed` (shown in Admin). Webhook `POST /api/webhooks/resend` (signature verified) records `delivered / bounced / complained`; hard bounces and complaints add to `email_suppression`, and later sends to that address are refused and shown to staff. Secrets: `RESEND_API_KEY` on `worker`, `RESEND_WEBHOOK_SECRET` on `api`, both via Railway after the 🚦 check.

**Tests.** Client with an injectable `httpx` transport; per-template rendering tests (subject, both bodies, escaping, host per environment); outbox idempotency (a retry never produces a second Resend call), backoff schedule, suppression refusal, QA allowlist; webhook valid/invalid signature, bounce → suppression. No test contacts Resend.

## 6. Admin Users tab and the prototype wiring

**Admin Users, live.** `GET /api/admin/users?state=&kind=&cursor=` (index `(state, submitted_at)`, ≤ 150 ms) feeds the design's table (Applicant · Affiliation and intent · Status · Decision) through the mapping module pattern of Map-engines Task M6; `POST /api/admin/users/{id}/decide {action ∈ approve|decline|request_info|suspend|revoke, note}` — note required for all but approve; re-auth for revoke; every decision audited and emailed. Reviewer hints (`flags[]`: disposable domain, employer keywords from a VIN Foundation list) render in the sub-line ("Affiliation flagged: …") and never decide anything. Seller applications appear with kind "Seller". Viewing an application detail is audited.

**Prototype wiring — the launch-removal list, in this order (zero-regression):**
1. Seed the design persona and add API sign-in to the visual harness `prepare()`; all design states green.
2. `logic.js`: `signIn` → `POST /api/auth/signin` (errors to `formError`); `submitApply` → `POST /api/applications`; `me` and `auth` from `/api/me`; gate `pending/rejected` from the account state — each change RED-then-GREEN against the characterisation suite (tests updated deliberately, never deleted).
3. Remove the jump bar markup, `gateStates` shortcuts, demo credentials and the `startViewport` query.
4. Sign-in copy "VIN username" → "Email" (design reference update; that string is masked in the gate-signin state until it lands).

## 7. Security requirements (from the red team)

S1 passwords-only compensations (§3) · S2 no enumeration (uniform responses, equal work, limits) · S3 hashed single-use tokens, POSTed from the landing page, `no-referrer` · S4 revocation on the next request (cache deleted in the same handler) · S5 escaped free text, PII retention, audited application views · S6 new session id on sign-in and privilege change; cookie flags; timeouts; reset revokes all · S7 outbox idempotency, QA allowlist, env-specific links, verified webhooks · S8 append-only audit without hashes/tokens · S9 one-release overlap of operator token and `require(perm)`; `api_token`s for automation · S10 bootstrap admin via one-time invite · S11 no state change on GET; Origin check · S12 proxy-hop IP only; email as primary limit key · S13 disposable-domain hint, never a block.

## 8. Performance requirements

Redis session cache (TTL 60 s, explicit invalidation), auth overhead ≤ 2 ms p95 · Argon2id in a thread, `m=64 MiB, t=3, p=1`, one hash ≤ 250 ms on CI · budgets in `tests/perf/test_api_latency.py`: `/api/me` ≤ 20 ms, `/api/auth/signin` ≤ 300 ms, `/api/auth/signup` ≤ 100 ms, `/api/admin/users` ≤ 150 ms · no email on the request path · `last_seen_at` ≤ once per 5 min · nightly session purge · k6 gains the sign-in flow at 5 VUs (p95 ≤ 400 ms).

## 9. Testing

Unit: password policy, token hashing/expiry, matrix rules, row filters, templates, `me.role` label. Integration: every auth endpoint's success path and each 4xx; uniform-response and timing checks (known vs unknown email within 20 ms); lockout; revocation on next request; CSRF/Origin; api tokens; the generated role × endpoint matrix; outbox/worker/webhook. E2E on QA: sign-up → verify (allowlist mailbox) → apply → staff approve → sign-in → browse as a member; the visual gate on the design persona. Everything test-first per the Quality and Performance Policy.

## 10. Plan impacts

Census plan: `require_member`/`auth_stub.py` → `require(perm)`; `MARKET_DATA_PUBLIC` → anonymous `market.read`; A9 `actor` → account id; C12 rotation replaced by deletion of `API_SECRET_KEY` after CI switches to `api_token`. Map-engines plan: `require_operator` → `require("licence.decide")`/`require("engine.activate")` with re-auth; `require_csrf` stays; `registry_change_log.actor` = account id; the Permissions tab joins the Admin tab set. Platform plan: `guard()` gains permissions; the visual harness gains API sign-in; the launch-removal list executes here. Migrations `010`–`015` (amended 2026-09-07: `016` is the Seed Listings plan's and `017`–`059` are Census SP3-A's).

## 11. Open items

Approval criteria wording (human decision confirmed) · consolidator/employer keyword list · `Reply-To` mailbox · retention for declined applications (proposed 12 months) and for the audit log · MFA before the first production admin · design deltas: sign-in copy "Email", Permissions tab · Resend DNS records (John) · meaning of "StartUp Club" (kept as free-text `affiliation_label`).

## 12. Definition of done

A real person can sign up with any email address on QA (allowlisted), verify, apply, be approved by a staff account, sign in and browse; Suspend removes access on the next request; every endpoint is in the matrix test and behaves per the table for all six roles; `auth_stub.py` and `API_SECRET_KEY` are gone from the code and from Railway; the visual gate is green on the design persona; latency and hash budgets hold; the audit log records every decision with actor and reason; no email leaves QA except to the allowlist.
