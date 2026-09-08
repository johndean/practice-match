# Wave 2a Task I5d — Launch sign-ups: admin read, CSV export, launch mail

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Wave 2a Task I5d (recorded here rather than in the identity plan, which is mid-execution on `feat/identity`).** Everything in this file belongs to Wave 2a and obeys the Identity spec's rules; it is a separate plan file only so that `docs/superpowers/plans/2026-09-05-practice-match-identity-access-email.md` is not edited while another branch is executing it. When that branch merges, this plan stays where it is and the identity plan gains one cross-reference line — not a copy.

**John's ruling (2026-09-08):** *"GO — Add Wave 2a Task I5d for the permission-gated Admin 'Launch sign-ups' read/export capability, CSV export API, and launch-mail step through the Resend pipeline. Also request the Rev 3 Admin 'Launch sign-ups' tab design."*

**Specs:** `docs/superpowers/specs/2026-09-06-coming-soon-production-mode-design.md` (§3 created `interest_signup`; §3 ends "No email is sent; the Identity wave's Resend pipeline (Wave 2a) reads this table for the launch notification" — this task is that sentence) and `docs/superpowers/specs/2026-09-05-identity-access-email-design.md` (§4 the permission matrix, §5 the Resend pipeline, §6 the admin surface, §8 the budgets). **Quality policy:** `docs/superpowers/specs/2026-09-05-quality-and-performance-policy.md`.

**Goal:** VIN Foundation staff can see, count, filter and export the launch-notification sign-ups collected by the Coming Soon page, and an admin can send — exactly once per address, from a re-authenticated session, through the existing outbox → Resend worker — the single message the page promised: *"One message, when it launches. Nothing else, and never shared."*

**Architecture:** Three permission-gated endpoints in one new router, `app/api/admin_signups.py`, mounted beside `app/api/admin_users.py`. The list is the keyset-paged shape `GET /api/admin/users` already established; the export is the same query rendered as a streamed RFC 4180 CSV; the launch mail writes one `email_outbox` row per sign-up and stamps `interest_signup.launch_mailed_at` in the SAME transaction, which is what makes "exactly once" survive a crash, a retry and a double click. No network call happens on the request path — the existing Celery `mail.send` task drains the outbox, applies `EMAIL_ALLOWLIST` outside production, and honours the suppression list, all unchanged. The Admin tab's UI is Task I5d.5 and does not start until the Rev 3 design exists.

**Tech Stack:** FastAPI, psycopg2 through `app.db.sync_conn()` (the pooled sync connection every admin handler uses), Starlette `StreamingResponse`, Python's `csv` module, the existing `app/mail/{templates,outbox,tasks}.py` pipeline, Celery 5, pytest against a per-session scratch Postgres, Playwright for the (gated) UI.

---

## Global Constraints (exact values — from the specs, CLAUDE.md and the quality policy)

- **TDD, no exceptions.** Every step that writes code starts from a test that is run and watched fail. `Run:` lines are mandatory and their expected RED output is written down.
- **Backend gate, exactly as CI runs it:** `docker compose -f docker-compose.dev.yml up -d && poetry run pytest -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100`, plus `ruff check .` and `mypy --strict`. 100 % of every line **and branch** of `app/` and `scripts/` (raised by P14, 2026-09-07); no exclusions without a ruling; no `noqa`, no `type: ignore`.
- **Frontend gate (Task I5d.5 only):** `npm run typecheck && npm test && npm run build`, then `npm run test:visual:baselines && npm run test:e2e`. Vitest at 100 % lines/branches/functions/statements on every hand-written file. Playwright `maxDiffPixels: 0`.
- **Every new route is classified.** `tests/auth/test_permissions.py::test_every_route_is_guarded_or_public` walks `create_app()`; a route is either guarded by a module-level `require(...)` constant or listed in `permissions.PUBLIC_ROUTES`. **Nothing in this task is public.**
- **Every guard is a module-level constant, never wrapped** (`deps.permission_of` resolves a route's permission by object identity).
- **`audit.write(` is called in each audited endpoint's OWN body**, never through a helper — `test_audited_permissions_are_written_by_their_handlers` reads `inspect.getsource(route.endpoint)`.
- **Every audited action is named after a permission** (`test_every_audited_action_is_named_after_a_permission`), so the actions written here are literally `"signups.export"` and `"signups.notify"`. No new entry in `MULTI_ACTION_PERMISSIONS` or `CASCADED_ACTIONS`.
- **The TypeScript twin is generated, never hand-edited:** `cd frontend && npm run gen:permissions` (which runs `python -m app.auth.permissions --ts`); `tests/auth/test_permissions.py::test_typescript_twin_is_current` diffs it.
- **An applied migration is IMMUTABLE.** `scripts/migrate.py` records each file's sha256 and exits 4 if it changed. `002_interest_signup.sql` has been applied to production and is never touched; this task adds a NEW file.
- **Migration number:** `003_launch_signups.sql`. The Census plan's D14 reserves `003`–`009` for "a Platform-level migration with no dependency on later tables"; this file only `ALTER`s `interest_signup`, which `002` creates, so it satisfies that rule exactly. `010`–`015` are Wave 2a's and already applied, `016` is the Seed Listings plan's, `017`–`059` are Census SP3-A's, `060`+ is SP3-B. The runner applies files in name order and skips what the ledger already holds, so a `003` landing after `015` is applied is ordinary.
- **A migration file contains no `BEGIN`/`COMMIT`/`ROLLBACK`** (the runner wraps each file and its ledger row in one transaction) and **no `CREATE INDEX CONCURRENTLY`** (the runner does not support statements that cannot run in a transaction).
- **No email on the request path.** The endpoint writes outbox rows and returns. `RESEND_API_KEY` lives on the `worker` service only.
- **`EMAIL_ALLOWLIST` outside production.** `app/mail/tasks.py::allowlisted()` already fails closed: on QA an empty allowlist sends to nobody and every refused row is recorded `suppressed` with `REASON_NOT_ALLOWLISTED`. This task changes none of that and adds a test that proves the launch template goes through it.
- **No test contacts Resend.** `tests/mail/test_send.py` injects an `httpx.MockTransport`; the API tests assert `email_outbox` rows and nothing else.
- **Outbox idempotency key** keeps the spec's `"{account_id}:{template}:{cause_id}"` shape: `f"{signup_id}:launch_announcement:1"`. A sign-up has no account, so its own id occupies the first slot; `1` is the cause, because there is exactly one launch.
- **Surgical diffs.** No refactor of `admin_users.py`, `outbox.py`, `tasks.py` or `resend_client.py` beyond the additive lines each step names. No function or feature is removed.
- **No invented UI.** The Admin tab has no design. Task I5d.5 is gated on the Rev 3 package and, when it arrives, is composed strictly through the D15 ruled-amendment mechanism (`docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md`, `frontend/tests/design-amendments.ts`).
- **Attribution and licence rules are untouched.** Nothing here renders a map or a Census figure.
- Every commit: conventional message, pathspecs spelled out, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Pushed to `origin` (vin-swe/practice-match) **and** `production` (johndean/practice-match). Work in a worktree on `feat/launch-signups`.
- **Versions in lockstep:** `frontend/package.json` and `pyproject.toml`, one patch per release (`tests/test_versions.py`), bumped once in Task I5d.4's commit.

---

## Decisions recorded in this plan (confirm on review)

| # | Decision | Why |
|---|---|---|
| **D-I5d-1** | Three permissions: `signups.read` = `{staff, admin}`, `signups.export` = `{staff, admin}`, `signups.notify` = `{admin}`. `signups.notify` joins `REAUTH`; `signups.export` and `signups.notify` join `AUDITED`; `signups.read` joins neither. | The matrix's observable rule (spec §4) is that **reading and reviewing** are staff+admin (`users.review`, `users.view_detail`, `data_sources.read`, `audit.read`, `permissions.read`) and the **irreversible or governing** actions are admin-only and re-authenticated (`licence.decide`, `engine.activate`, `roles.grant`, `tokens.manage`, plus `users.revoke`). A one-shot mass mail that cannot be unsent is the second kind. `signups.read` is NOT audited for the reason C2 gave in the I5 fix round: the list is polled by a tab, and one audit row per poll writes into a table whose triggers refuse DELETE. `signups.export` IS audited because a bulk export of every address is one bounded, deliberate act. |
| **D-I5d-2** | `signups.notify` in `REAUTH` also means **no automation token can ever trigger the launch mail** (`deps.TokenCannotReauth`). This is a wanted property, not a side effect. | A leaked `admin` api token must not be able to mail the VIN Foundation's entire launch list. |
| **D-I5d-3** | `TOKEN_DENIED` is **not** widened to include `signups.export`. | `TOKEN_DENIED` is one narrow rule about a credential minting its own successor; widening it is a policy change nobody has asked for. A staff/admin token can only be minted by an admin under re-auth (`may_mint`), and every export writes an audit row. Flagged to John as an open question rather than decided in code. |
| **D-I5d-4** | Idempotency is a **`launch_mailed_at timestamptz` column on `interest_signup`**, not a send-ledger table and not the outbox's own unique key. | The outbox is not a durable ledger: `app/mail/tasks.py::purge_outbox` deletes `sent` rows 24 hours after delivery (`SENT_TTL_S`), so a second `launch-mail` call the next day would find no `idempotency_key` conflict and re-mail everyone. A separate ledger table would be a third place recording one fact about a row that already exists. One nullable column, written in the same transaction as the `enqueue`, is the smallest thing that cannot come apart. |
| **D-I5d-5** | The router is mounted in **both** site modes, unlike `admin_users_router`; the real send is refused with `409 NOT_LAUNCHED` while `SITE_MODE != "app"`, and the **dry run is allowed in coming-soon mode**. | The rows only exist on production, and production runs `coming_soon` until launch, so gating the router the way `admin_users` is gated would make the whole capability unreachable exactly where the data is. Every route is `require(...)`-guarded, so in coming-soon mode the only credential that resolves is the legacy `API_SECRET_KEY` bearer (there is no sign-in route and no way to mint a token on production), which is already admin-equivalent by construction and is deleted in Task I9. The one action that could do harm — the mail whose copy says the site is open — is refused until the site actually is. Risk stated for John in Open Questions. |
| **D-I5d-6** | The `source=` / `consent_version=` filters are validated against the values **actually present in the table**, computed by the same grouped query that produces `counts`, not against a hard-coded enum. | F10's lesson was that an unknown filter must be a `422 BAD_FILTER`, not a silent empty page. But both columns are free `text` with no CHECK constraint, and a future Coming Soon variant will add a `source`; a hard-coded tuple would 422 a legitimate value. Deriving the allowed set from the data gives F10's behaviour with nothing to keep in step by hand. |
| **D-I5d-7** | The CSV carries **no UTF-8 BOM**. Fields whose first character is `=`, `+`, `-`, `@`, TAB or CR are prefixed with a single apostrophe (`'`). | RFC 4180 and `charset=utf-8` describe the file exactly; a BOM would make a strict parser read the first header cell as `﻿id`. The apostrophe is the OWASP mitigation for spreadsheet formula injection, and it is needed here for a real reason: `app/api/interest.py`'s `EMAIL_RE` accepts an address beginning with `=` or `+`. The untransformed value is always available from `GET /api/admin/signups`, which is the JSON source of truth. |
| **D-I5d-8** | The export uses an ordinary client-side cursor and streams the rendered rows, capped at `MAX_EXPORT = 100_000`. | `sync_conn()` hands out an **autocommit** pooled connection, and psycopg2 refuses a named (server-side) cursor outside a transaction — `with conn:` does not open one when `autocommit` is True. Taking a non-autocommit connection just for this would mutate a pooled object. At the list's real scale (a launch-notification list, thousands of rows) the result set is tens of KB per thousand rows; the response is still streamed, so no whole-file string is ever built. The upgrade path, if the table ever outgrows the cap, is a dedicated non-pooled connection with `autocommit = False` and a named cursor — written down here so nobody has to rediscover the autocommit trap. |
| **D-I5d-9** | `POST /api/admin/signups/launch-mail` acts on at most `MAX_LAUNCH_BATCH = 500` rows per call and reports `remaining`. | The handler holds one pooled connection for the length of its transaction; an unbounded call would write tens of thousands of outbox rows under it. 500 is also one clean unit for the (gated) UI to show progress against. |
| **D-I5d-10** | `dry_run` defaults to `true`. A caller must send `{"dry_run": false}` to actually queue anything. | The safe default for an action that cannot be undone. |
| **D-I5d-11** | The keyset cursor helpers `_cursor`, `_keyset` and `_iso` are **imported from `app.api.admin_users`**, not copied (`BadCursor` is raised through `_keyset` and is never named here, so it is not imported). | F3 was a real defect — a cursor carrying only a timestamp dropped every row sharing the last row's timestamp and then reported the list complete (3 of 6 accounts returned on the shipped code). One implementation, one place it can be got wrong. Copying it and adding a drift test would be the alternative; importing is smaller and cannot drift at all. |

---

## File map

| File | Responsibility | Task |
|---|---|---|
| `app/auth/permissions.py` | `signups.read` / `signups.export` / `signups.notify` in `MATRIX`; `signups.notify` in `REAUTH`; both write permissions in `AUDITED` | I5d.1 |
| `frontend/src/auth/permissions.ts` | regenerated twin (never hand-edited) | I5d.1 |
| `migrations/003_launch_signups.sql` | `interest_signup.launch_mailed_at`; the listing index and the partial unmailed index | I5d.2 |
| `app/api/admin_signups.py` | **new** — `GET /api/admin/signups`, `GET /api/admin/signups.csv`, `POST /api/admin/signups/launch-mail` | I5d.3, I5d.4 |
| `app/main.py` | one `include_router` line, outside the `site_mode == "app"` block (D-I5d-5) | I5d.3 |
| `app/mail/templates.py` | the `launch_announcement` template (subject, text, HTML) | I5d.4 |
| `app/mail/outbox.py` | `"launch_announcement"` in `TEMPLATES` | I5d.4 |
| `tests/auth/test_permissions.py` | the three permissions and their three set memberships | I5d.1 |
| `tests/test_migrate.py` | `003`'s column and its two indexes | I5d.2 |
| `tests/api/test_admin_signups.py` | **new** — every case for the three endpoints | I5d.3, I5d.4 |
| `tests/mail/test_templates.py` | the fifteenth key; the launch copy | I5d.4 |
| `tests/mail/test_send.py` | a `launch_announcement` row through the allowlist and the suppression list | I5d.4 |
| `tests/perf/test_api_latency.py` | `/api/admin/signups` joins `BUDGET_MS` and `STAFF_PATHS` at 150 ms | I5d.3 |
| `tests/perf/test_query_plans.py` | `signups_list` joins `PLANS`/`INDEXES`/`SEEDS` | I5d.3 |
| `docs/RUNBOOK-identity.md` | §12 "The launch email" — the operator page, drift-tested against the route table | I5d.4 |
| `docs/design-reference/requests/2026-09-08-rev3-admin-launch-signups-tab.md` | the design request John hands the Rev 3 designer (written with this plan; not code) | — |
| `frontend/src/admin/signups.ts`, `frontend/tests/screens.ts`, `frontend/tests/design-amendments.ts`, `LOCAL_AMENDMENTS.md` | the Admin tab — **only after the Rev 3 design lands** | I5d.5 |

---

## Preconditions (run these first; every one must pass before Step 1 of Task I5d.1)

```bash
cd "$(git rev-parse --show-toplevel)"
docker compose -f docker-compose.dev.yml up -d
grep -n '"users.review": _STAFF' app/auth/permissions.py                  # the matrix is where this plan says it is
grep -n 'REQUIRE_REVIEW = require("users.review")' app/api/admin_users.py  # module-level guard constants
grep -n 'def enqueue' app/mail/outbox.py                                   # the outbox writer
grep -n 'def allowlisted' app/mail/tasks.py                                # the QA allowlist gate
grep -n 'def purge_sent' app/mail/outbox.py                                # D-I5d-4's reason
ls migrations/003_*.sql 2>/dev/null && echo "STOP: 003 is taken" || echo "003 is free"
grep -n 'interest_signup' migrations/002_interest_signup.sql
poetry run pytest -q tests/auth/test_permissions.py                        # green before anything moves
```

Expected: every `grep` hits; `003 is free`; the permissions suite is green. If `003` is taken, stop and ask — the number is a decision, not an implementation detail.

---

### Task I5d.1: The three permissions, the regenerated twin, the matrix tests

*Standard-tier implementer. No route exists yet, so this task adds capability names and nothing that uses them; Task I5d.3 and I5d.4 consume them.*

**Files:**
- Modify: `app/auth/permissions.py` (`MATRIX`, `REAUTH`, `AUDITED`), `frontend/src/auth/permissions.ts` (**generated** — never hand-edited)
- Test: `tests/auth/test_permissions.py`

**Interfaces:**
- Consumes: `_STAFF = frozenset({"staff", "admin"})`, `_ADMIN = frozenset({"admin"})`, `MATRIX`, `REAUTH`, `AUDITED`, `ADMINISTRATIVE` (derived: every row whose holders `<= _STAFF`), `to_typescript()`.
- Produces: `MATRIX["signups.read"] == frozenset({"staff", "admin"})`, `MATRIX["signups.export"] == frozenset({"staff", "admin"})`, `MATRIX["signups.notify"] == frozenset({"admin"})`; `"signups.notify" in REAUTH`; `{"signups.export", "signups.notify"} <= AUDITED`; all three in `ADMINISTRATIVE` by derivation.
- Unchanged: `TOKEN_DENIED` (D-I5d-3), `PUBLIC_ROUTES`, `may_mint`, `effective_roles`, `allowed`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/auth/test_permissions.py — append, beside test_matrix_matches_the_spec_table

def test_the_launch_signup_permissions_read_staff_export_staff_notify_admin():
    """Task I5d (John, 2026-09-08). The matrix's own rule, applied: reading and reviewing are
    staff+admin (`users.review`, `data_sources.read`, `audit.read`); the irreversible, governing
    actions are admin-only and re-authenticated (`roles.grant`, `tokens.manage`, `users.revoke`).
    A launch mail cannot be unsent, so it is the second kind."""
    assert PM.MATRIX["signups.read"] == frozenset({"staff", "admin"})
    assert PM.MATRIX["signups.export"] == frozenset({"staff", "admin"})
    assert PM.MATRIX["signups.notify"] == frozenset({"admin"})


def test_the_launch_mail_is_re_authenticated_and_therefore_out_of_every_api_tokens_reach():
    """D-I5d-2: `signups.notify` in REAUTH is also the containment. `deps.require` refuses a token
    principal on any REAUTH permission with `TokenCannotReauth`, so no automation credential — not
    even a leaked `admin` one — can mail the VIN Foundation's entire launch list."""
    assert "signups.notify" in PM.REAUTH
    assert "signups.read" not in PM.REAUTH and "signups.export" not in PM.REAUTH


def test_the_bulk_export_and_the_launch_mail_are_audited_and_the_polled_list_is_not():
    """The C2 rule (I5 fix round 1) applied to this tab: the LIST is polled by a screen and must
    not write one `audit_log` row per poll into a table whose triggers refuse DELETE. The export
    and the send are each one bounded, deliberate act, and both leave a row."""
    assert {"signups.export", "signups.notify"} <= PM.AUDITED
    assert "signups.read" not in PM.AUDITED


def test_the_launch_signup_permissions_are_administrative_by_derivation():
    """`ADMINISTRATIVE` is derived from the matrix, never listed, so this is a check that the three
    rows really are staff-or-narrower — which is what keeps `may_mint` from letting a member-role
    token administer the sign-up list."""
    assert {"signups.read", "signups.export", "signups.notify"} <= PM.ADMINISTRATIVE


def test_token_denied_is_unchanged_by_task_i5d():
    """D-I5d-3, written down so a later widening has to argue for itself in a diff. `tokens.manage`
    is still the only permission subtracted from a token principal's set."""
    assert PM.TOKEN_DENIED == frozenset({"tokens.manage"})
```

- [ ] **Step 2: Run — RED**

```bash
poetry run pytest -q tests/auth/test_permissions.py -k "launch or token_denied_is_unchanged"
```

Expected: four failures with `KeyError: 'signups.read'` (and `'signups.export'`, `'signups.notify'`) out of `PM.MATRIX[...]`, plus the two set-membership assertions failing. `test_token_denied_is_unchanged_by_task_i5d` passes already — it is a pin, not a driver.

- [ ] **Step 3: Implement**

In `app/auth/permissions.py`, add one block to `MATRIX` immediately after the `data_sources.read` line (the other admin-tab read), and one name to each of `REAUTH` and `AUDITED`:

```python
    # The Coming Soon launch-notification list (Task I5d, John 2026-09-08). `interest_signup` is
    # filled by the public page on production; these three are what staff and admins may do with
    # it. Split three ways rather than one `signups.manage` because the three acts have genuinely
    # different blast radii: reading a page of the list is a screen refreshing, exporting every
    # address is a file leaving the building, and sending the mail cannot be undone.
    "signups.read": _STAFF, "signups.export": _STAFF,
    "signups.notify": _ADMIN,
```

```python
REAUTH = frozenset({"licence.decide", "engine.activate", "roles.grant", "tokens.manage", "users.revoke", "signups.notify"})
```

```python
AUDITED = frozenset({"users.view_detail", "users.decide", "users.revoke", "roles.grant", "tokens.manage", "licence.decide", "engine.activate", "abuse.investigate", "signups.export", "signups.notify"})
```

Add one sentence to the comment block above `REAUTH`, in the same voice as the `users.revoke` note beside it:

```python
# "signups.notify" joins the list in Task I5d (John, 2026-09-08): the launch mail is one
# irreversible message to every address the Coming Soon page ever collected, which is at least as
# consequential as a revocation — and re-auth is also what keeps every api token out of it
# (`deps.TokenCannotReauth`), so no automation credential can ever send it.
```

- [ ] **Step 4: Regenerate the twin and run — GREEN**

```bash
cd frontend && npm run gen:permissions && cd ..
git diff --stat frontend/src/auth/permissions.ts        # expect: 3 MATRIX lines, the Permission union, REAUTH
poetry run pytest -q tests/auth/test_permissions.py tests/auth/test_matrix.py
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
poetry run ruff check . && poetry run mypy --strict app scripts
cd frontend && npm run typecheck && npm test && cd ..
```

Expected: green everywhere. `tests/auth/test_matrix.py` generates its rows from the running app, so it needs no edit — the three permissions guard no route yet and simply do not appear. `frontend/src/admin/permissions.ts::toPermissionRows` derives its rows from the matrix, so the read-only Permissions tab gains three rows with **empty** Meaning cells; that is correct today and is exactly what §2 of the Rev 3 design request asks John's designer to fill.

- [ ] **Step 5: Commit**

```bash
git add app/auth/permissions.py frontend/src/auth/permissions.ts tests/auth/test_permissions.py
git commit -m "$(cat <<'EOF'
feat(identity): signups.read/export/notify permissions for the launch sign-up list

Wave 2a Task I5d (John, 2026-09-08). Read and export are staff+admin, the
launch mail is admin-only and re-authenticated — which also puts it out of
every api token's reach. Export and send are audited; the polled list is not
(the C2 rule: one row per poll into an append-only table).

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
git push origin HEAD && git push production HEAD
```

---

**Controller amendment A-I5d.1 (2026-09-08; ruling on I5d.1's NEEDS_CONTEXT).** The brief's Step 4 claim that `tests/auth/test_matrix.py` "needs no edit" was false: `test_a_minter_may_never_mint_a_token_that_administers_more_than_it_does` pins the exact `ADMINISTRATIVE` set (16 → 19 with the three signups permissions) and `test_every_reauth_permission_is_either_swept_or_listed_with_its_reason` requires every no-route `REAUTH` permission to be listed in `REAUTH_OUTSIDE_THE_SWEEP` with a reason. Both pins are amended in I5d.1 (RED observed as the two failures), `signups.notify` listed as "no route yet (I5d.4 mounts POST /api/admin/signups/launch-mail)"; I5d.4 removes that entry when the route mounts (add to I5d.4's steps). Files list of I5d.1 gains `tests/auth/test_matrix.py`.

---

### Task I5d.2: `migrations/003_launch_signups.sql` — the idempotency column and the two indexes

*Standard-tier implementer. Schema only; no Python changes.*

**Files:**
- Create: `migrations/003_launch_signups.sql`
- Test: `tests/test_migrate.py` (append, beside `test_002_creates_interest_signup_with_a_unique_normalised_email`)

**Interfaces:**
- Consumes: `migrations/002_interest_signup.sql`'s `interest_signup` table; `tests/conftest.py`'s `scratch_db` / `conn` fixtures (a scratch database with every migration applied); `scripts/migrate.py`'s name-ordered, checksum-guarded runner.
- Produces: `interest_signup.launch_mailed_at timestamptz NULL`; `interest_signup_listing_idx (created_at DESC, id DESC)`; `interest_signup_unmailed_idx (id) WHERE launch_mailed_at IS NULL`.
- **Does not** touch `002`. That file's sha256 is in the production ledger and `scripts/migrate.py` exits 4 on a changed applied file.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_migrate.py — append

def test_003_adds_launch_mailed_at_and_its_two_indexes(scratch_db):
    """Task I5d. `launch_mailed_at` is the whole of the launch mail's exactly-once guarantee
    (D-I5d-4): the outbox cannot be the ledger, because `purge_outbox` deletes delivered rows 24
    hours after they are sent, so a second call the next day would find no idempotency conflict.

    A NEW file rather than an edit to `002`: `002` is applied on production and the runner records
    its sha256, so editing it would stop the next deploy with exit 4. `003` is inside the range the
    Census plan's D14 reserves for Platform-level migrations with no dependency on later tables,
    which is exactly what an ALTER of a `002` table is."""
    with psycopg2.connect(scratch_db) as conn, conn.cursor() as cur:
        cur.execute("""SELECT data_type, is_nullable FROM information_schema.columns
                        WHERE table_name = 'interest_signup' AND column_name = 'launch_mailed_at'""")
        assert cur.fetchone() == ("timestamp with time zone", "YES")
        cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'interest_signup'")
        names = {r[0] for r in cur.fetchall()}
        assert {"interest_signup_listing_idx", "interest_signup_unmailed_idx"} <= names


def test_003_defaults_launch_mailed_at_to_null_so_every_existing_row_is_unmailed(scratch_db):
    """The production table already holds rows. They must all read as "not yet mailed" — a DEFAULT
    now() would have marked every one of them as already told, and the promised message would never
    have been sent to a single person who signed up before this migration."""
    with psycopg2.connect(scratch_db) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO interest_signup (email, email_normalised, consent_version) "
                    "VALUES ('a@x.com', 'a@x.com', 'coming-soon-v1') RETURNING launch_mailed_at")
        assert cur.fetchone()[0] is None


def test_003_contains_no_transaction_control_and_no_concurrent_index():
    """`scripts/migrate.py` wraps each file and its ledger row in ONE transaction, so a file that
    opens its own is a runner error; and the runner does not support statements that cannot run in
    a transaction at all. Both rules are in the runner's docstring; this is what holds this file
    to them.

    Comments are stripped before the scan — the file's own header explains why it contains no
    `CREATE INDEX CONCURRENTLY`, and a naive substring search would trip over that explanation."""
    path = Path(__file__).resolve().parent.parent / "migrations" / "003_launch_signups.sql"
    statements = "\n".join(line.split("--", 1)[0] for line in path.read_text().splitlines()).upper()
    for forbidden in ("BEGIN", "COMMIT", "ROLLBACK", "CONCURRENTLY"):
        assert forbidden not in statements, forbidden
```

> `scratch_db` is `tests/test_migrate.py`'s own fixture (a fresh database with every migration applied). `Path` is already imported there; if it is not, add the import with the tests.

- [ ] **Step 2: Run — RED**

```bash
poetry run pytest -q tests/test_migrate.py -k "003"
```

Expected: `assert None == ('timestamp with time zone', 'YES')` (the column does not exist), and `FileNotFoundError: migrations/003_launch_signups.sql` on the third.

- [ ] **Step 3: Write the migration**

```sql
-- Wave 2a Task I5d (John, 2026-09-08): the Admin "Launch sign-ups" capability.
--
-- `002_interest_signup.sql` is applied on production and its sha256 is in that database's ledger,
-- so it is never edited (scripts/migrate.py exits 4 on a changed applied file). This file is the
-- amendment. It is numbered 003 because the Census plan's D14 reserves 003-009 for Platform-level
-- migrations with no dependency on later tables, and an ALTER of a 002 table is precisely that;
-- the runner applies files in name order and skips what the ledger holds, so landing after
-- 010-015 is ordinary.
--
-- No BEGIN/COMMIT (the runner wraps this file and its ledger row in one transaction) and no
-- CREATE INDEX CONCURRENTLY (the runner cannot run a statement outside a transaction). The table
-- is a launch-notification list of a few thousand rows, so the brief ACCESS EXCLUSIVE lock the two
-- CREATE INDEX statements take is measured in milliseconds.

-- Exactly-once for the launch mail. NULL means "not yet mailed", which is what every row that
-- already exists must read as: a DEFAULT here would silently mark the whole existing list as
-- already told, and nobody who signed up before today would ever get the message they were
-- promised. Stamped in the SAME transaction as the email_outbox row, so a crash can neither mail
-- twice nor mark a row mailed without its outbox row.
ALTER TABLE interest_signup ADD COLUMN IF NOT EXISTS launch_mailed_at timestamptz;

-- The admin list's ORDER BY and the keyset the cursor pages on — the same column order as
-- `account_listing_idx` in 015, for the same reason: the index serves the sort as well as the
-- lookup, and a keyset cursor of (created_at, id) must not fall back to a sort of the whole table.
CREATE INDEX IF NOT EXISTS interest_signup_listing_idx ON interest_signup (created_at DESC, id DESC);

-- The launch mail's own scan: `WHERE launch_mailed_at IS NULL ORDER BY id LIMIT n FOR UPDATE`.
-- Partial, because the interesting set shrinks to zero as the send completes and a full index on
-- a column that is NULL for every row would be all of it.
CREATE INDEX IF NOT EXISTS interest_signup_unmailed_idx ON interest_signup (id) WHERE launch_mailed_at IS NULL;
```

- [ ] **Step 4: Run — GREEN**

```bash
poetry run pytest -q tests/test_migrate.py
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
```

Expected: green. Note that the `conn`/`scratch_dsn` fixtures build a fresh database from `migrations/` for each test, so every later task's tests see the column from here on.

- [ ] **Step 5: Commit**

```bash
git add migrations/003_launch_signups.sql tests/test_migrate.py
git commit -m "$(cat <<'EOF'
feat(db): interest_signup.launch_mailed_at and the launch sign-up list indexes

Wave 2a Task I5d. A NEW migration, not an edit to 002: 002 is applied on
production and the ledger records its sha256. 003 is inside the range D14
reserves for Platform-level migrations with no dependency on later tables.

launch_mailed_at is NULL for every existing row, which is what makes the
promised message reach the people who signed up before today. It is the
launch mail's exactly-once ledger because the outbox is not one — purge_outbox
deletes delivered rows 24 hours after they are sent.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
git push origin HEAD && git push production HEAD
```

---

### Task I5d.3: `GET /api/admin/signups` and `GET /api/admin/signups.csv`

*Standard-tier implementer. The read half: paged list with counts and filters, and the streamed CSV export.*

**Files:**
- Create: `app/api/admin_signups.py`, `tests/api/test_admin_signups.py`
- Modify: `app/main.py` (one `include_router` line, outside the `site_mode == "app"` block), `tests/perf/test_api_latency.py` (`BUDGET_MS`, `STAFF_PATHS`), `tests/perf/test_query_plans.py` (`PLANS`, `INDEXES`, `SEEDS`)

**Interfaces:**
- Consumes: `app.auth.deps.require`, `app.auth.audit.write`, `app.auth.sessions.Principal`, `app.db.sync_conn`, `app.auth.deps.AuthError`, and — imported, never copied (D-I5d-11) — `app.api.admin_users`'s `_cursor`, `_keyset`, `_iso` (`_keyset` raises that module's `BadCursor`, which is never named here).
- Produces:
  - `GET /api/admin/signups?source=&consent_version=&cursor=&limit=` → `200`
    ```json
    {
      "items": [{"id": "<uuid>", "email": "a@x.com", "source": "coming-soon",
                 "consent_version": "coming-soon-v1", "created_at": "2026-09-01T12:00:00+00:00",
                 "launch_mailed_at": null}],
      "next_cursor": "2026-09-01T12:00:00Z|<uuid>",
      "counts": {"total": 1830, "launch_mailed": 0, "not_mailed": 1830, "filtered": 1830,
                 "by_source": {"coming-soon": 1830},
                 "by_consent_version": {"coming-soon-v1": 1830}}
    }
    ```
    `limit` defaults to 50 and is capped at `MAX_LIST = 200`; `next_cursor` is `null` on the last page. Refusals: `401` unauthenticated, `403` without `signups.read`, `422 BAD_CURSOR`, `422 BAD_FILTER`.
  - `GET /api/admin/signups.csv?source=&consent_version=` → `200`, `Content-Type: text/csv; charset=utf-8`, `Content-Disposition: attachment; filename="practice-match-signups-YYYY-MM-DD.csv"`, RFC 4180 body: CRLF line endings, `QUOTE_MINIMAL`, doubled quotes, header row `id,email,source,consent_version,created_at,launch_mailed_at`. One audit row (`signups.export`) written **before** the first byte streams.
- Unchanged: every other router; `permissions.PUBLIC_ROUTES` (both routes are guarded).

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_admin_signups.py (new)
"""Task I5d — the Admin "Launch sign-ups" read surface.

`client` here is `tests/api/conftest.py`'s: it speaks over `https://qa.foundation.vin`, which is
what `check_origin_and_csrf` compares against. `member(roles=..., state=...)` returns
`(account_id, cookies, headers)`; `auth_headers(cookies, headers)` turns those into a literal
`Cookie` header (httpx 0.28 deprecates per-request `cookies=`, and `-W error` makes that a failure).
"""
import csv
import inspect
import io
from datetime import UTC, datetime

import pytest

from app.config import settings
from tests.api.conftest import auth_headers

SIGNUPS = "/api/admin/signups"


def seed(conn, n, *, prefix="S", source="coming-soon", consent="coming-soon-v1", mailed=False):
    """`n` sign-ups a minute apart, newest last, so the list's DESC order and the keyset cursor
    both have something to be wrong about.

    `prefix` because `interest_signup.email_normalised` is UNIQUE: a test that seeds twice must
    give the second batch its own addresses or the second INSERT raises."""
    ids = []
    with conn.cursor() as cur:
        for i in range(n):
            cur.execute(
                "INSERT INTO interest_signup (email, email_normalised, consent_version, source, created_at, launch_mailed_at) "
                "VALUES (%s,%s,%s,%s, now() - (%s || ' minutes')::interval, %s) RETURNING id",
                (f"{prefix}{i}@x.test", f"{prefix.lower()}{i}@x.test", consent, source, n - i,
                 datetime.now(UTC) if mailed else None))
            ids.append(cur.fetchone()[0])
    return ids


@pytest.fixture
def staff_headers(member):
    _, cookies, headers = member(roles=("staff",))
    return auth_headers(cookies, headers)


@pytest.fixture
def buyer_headers(member):
    _, cookies, headers = member(roles=("buyer",))
    return auth_headers(cookies, headers)


async def test_the_list_is_newest_first_with_the_stored_address_and_the_mailed_stamp(client, conn, staff_headers):
    seed(conn, 3)
    r = await client.get(SIGNUPS, headers=staff_headers)
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["email"] for i in items] == ["S2@x.test", "S1@x.test", "S0@x.test"]   # newest first
    assert items[0]["source"] == "coming-soon" and items[0]["consent_version"] == "coming-soon-v1"
    assert items[0]["launch_mailed_at"] is None


async def test_the_counts_describe_the_whole_table_and_the_current_filter(client, conn, staff_headers):
    seed(conn, 2, mailed=True)
    seed(conn, 3, prefix="P", source="partner-page")
    counts = (await client.get(SIGNUPS, headers=staff_headers)).json()["counts"]
    assert counts["total"] == 5 and counts["launch_mailed"] == 2 and counts["not_mailed"] == 3
    assert counts["by_source"] == {"coming-soon": 2, "partner-page": 3}
    assert counts["by_consent_version"] == {"coming-soon-v1": 5}
    assert counts["filtered"] == 5
    filtered = (await client.get(f"{SIGNUPS}?source=partner-page", headers=staff_headers)).json()
    assert [i["source"] for i in filtered["items"]] == ["partner-page"] * 3
    assert filtered["counts"]["filtered"] == 3 and filtered["counts"]["total"] == 5


async def test_a_filter_value_that_is_in_no_row_is_a_422_naming_the_values_that_are(client, conn, staff_headers):
    """F10's rule, with D-I5d-6's twist: the allowed set is the data, not a hard-coded enum, so a
    future `source` needs no code change and a typo still reads as "no such filter"."""
    seed(conn, 1)
    r = await client.get(f"{SIGNUPS}?source=comingsoon", headers=staff_headers)
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "BAD_FILTER" and "coming-soon" in body["message"]


async def test_the_cursor_pages_without_dropping_a_row_when_timestamps_tie(client, conn, staff_headers):
    """F3, in this table. `now()` is transaction time, so a bulk import ties every row's
    `created_at`; a cursor carrying only the timestamp drops every tied row and then reports the
    list complete."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO interest_signup (email, email_normalised, consent_version) "
                    "SELECT 'T'||i||'@x.test', 't'||i||'@x.test', 'coming-soon-v1' FROM generate_series(1,6) i")
    seen, cursor = [], None
    for _ in range(6):
        page = (await client.get(f"{SIGNUPS}?limit=2" + (f"&cursor={cursor}" if cursor else ""), headers=staff_headers)).json()
        seen += [i["id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 6 and len(set(seen)) == 6 and cursor is None


async def test_a_malformed_cursor_is_a_422_not_a_500(client, conn, staff_headers):
    seed(conn, 1)
    r = await client.get(f"{SIGNUPS}?cursor=nonsense", headers=staff_headers)
    assert r.status_code == 422 and r.json()["error"]["code"] == "BAD_CURSOR"


async def test_limit_is_capped(client, conn, staff_headers):
    seed(conn, 3)
    r = await client.get(f"{SIGNUPS}?limit=100000", headers=staff_headers)
    assert r.status_code == 200 and len(r.json()["items"]) == 3


async def test_the_list_needs_signups_read(client, conn, buyer_headers):
    seed(conn, 1)
    assert (await client.get(SIGNUPS, headers=buyer_headers)).status_code == 403
    assert (await client.get(SIGNUPS)).status_code == 401


async def test_reading_the_list_writes_no_audit_row(client, conn, staff_headers):
    """The C2 rule: this list is polled by a screen, and `audit_log`'s triggers refuse DELETE."""
    seed(conn, 1)
    await client.get(SIGNUPS, headers=staff_headers)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM audit_log WHERE action LIKE 'signups.%'")
        assert cur.fetchone()[0] == 0


# --- the CSV export ---------------------------------------------------------------------------

async def test_the_export_is_rfc4180_utf8_with_a_header_row_and_one_row_per_signup(client, conn, staff_headers):
    seed(conn, 2)
    r = await client.get("/api/admin/signups.csv", headers=staff_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv") and "charset=utf-8" in r.headers["content-type"]
    assert r.headers["content-disposition"].startswith('attachment; filename="practice-match-signups-')
    body = r.content.decode("utf-8")
    assert not body.startswith("﻿"), "no BOM (D-I5d-7): it would make the first header cell '\\ufeffid'"
    assert "\r\n" in body and body.endswith("\r\n")
    rows = list(csv.reader(io.StringIO(body)))
    assert rows[0] == ["id", "email", "source", "consent_version", "created_at", "launch_mailed_at"]
    assert [r[1] for r in rows[1:]] == ["S1@x.test", "S0@x.test"]
    assert len(rows) == 3


async def test_the_export_quotes_a_comma_and_doubles_an_embedded_quote(client, conn, staff_headers):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO interest_signup (email, email_normalised, consent_version, source) "
                    """VALUES ('a@x.test', 'a@x.test', 'coming-soon-v1', 'campaign,"spring"')""")
    body = (await client.get("/api/admin/signups.csv", headers=staff_headers)).content.decode("utf-8")
    assert '"campaign,""spring"""' in body
    assert list(csv.reader(io.StringIO(body)))[1][2] == 'campaign,"spring"'


async def test_a_field_that_would_be_a_spreadsheet_formula_is_neutralised(client, conn, staff_headers):
    """D-I5d-7. `app/api/interest.py`'s EMAIL_RE accepts an address beginning with `=` or `+`, so
    this is a real value this table can hold, not a hypothetical. The untransformed value stays
    available from the JSON list, which is the source of truth."""
    with conn.cursor() as cur:
        cur.execute("INSERT INTO interest_signup (email, email_normalised, consent_version) "
                    "VALUES ('=1+1@x.test', '=1+1@x.test', 'coming-soon-v1')")
    body = (await client.get("/api/admin/signups.csv", headers=staff_headers)).content.decode("utf-8")
    assert list(csv.reader(io.StringIO(body)))[1][1] == "'=1+1@x.test"
    listed = (await client.get(SIGNUPS, headers=staff_headers)).json()["items"][0]
    assert listed["email"] == "=1+1@x.test"


async def test_the_export_honours_the_same_filters_as_the_list(client, conn, staff_headers):
    seed(conn, 2)
    seed(conn, 1, prefix="P", source="partner-page")
    body = (await client.get("/api/admin/signups.csv?source=partner-page", headers=staff_headers)).content.decode("utf-8")
    assert len(list(csv.reader(io.StringIO(body)))) == 2      # header + one row


async def test_the_export_needs_signups_export_and_leaves_exactly_one_audit_row(client, conn, staff_headers, buyer_headers):
    seed(conn, 3)
    assert (await client.get("/api/admin/signups.csv", headers=buyer_headers)).status_code == 403
    await client.get("/api/admin/signups.csv?source=coming-soon", headers=staff_headers)
    with conn.cursor() as cur:
        cur.execute("SELECT action, target_type, after FROM audit_log WHERE action = 'signups.export'")
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "interest_signup" and rows[0][2] == {"source": "coming-soon", "consent_version": None}
```

Add to `tests/perf/test_api_latency.py`:

```python
BUDGET_MS = {"/api/healthz": 20, "/": 15, "/api/me": 20,
             "/api/admin/users?state=pending": 150,
             # Task I5d: the other administrative READ a reviewer waits on, budgeted with the
             # queue it sits beside (spec §8). Same caveat as the line above — this gates the code
             # path, not the plan; `tests/perf/test_query_plans.py::signups_list` gates the plan.
             "/api/admin/signups": 150}
STAFF_PATHS = frozenset({"/api/admin/users?state=pending", "/api/admin/signups"})
```

Add to `tests/perf/test_query_plans.py`:

```python
from app.api.admin_signups import LIST_SQL as SIGNUPS_LIST_SQL
from app.api.admin_signups import MAX_LIST as SIGNUPS_MAX_LIST

PLANS["signups_list"] = (
    "EXPLAIN (FORMAT JSON) " + SIGNUPS_LIST_SQL,
    {"source": None, "consent_version": None, "cursor_at": None, "cursor_id": None, "limit": SIGNUPS_MAX_LIST + 1},
)
INDEXES["signups_list"] = ("interest_signup_listing_idx",)


def _seed_signups(conn):
    """2,000 sign-ups a minute apart, then ANALYZE — without rows and statistics the planner sorts
    a 10-page estimate and the index assertion is a coin toss."""
    with conn.cursor() as cur:
        cur.execute("""INSERT INTO interest_signup (email, email_normalised, consent_version, source, created_at)
                       SELECT 'plan-'||i||'@x.test', 'plan-'||i||'@x.test', 'coming-soon-v1', 'coming-soon',
                              now() - (i || ' minutes')::interval
                         FROM generate_series(1, 2000) i""")
        cur.execute("ANALYZE interest_signup")


SEEDS["signups_list"] = _seed_signups
```

> If `PLANS`, `INDEXES` and `SEEDS` are written as literal dict displays in that file, add the three entries **inside** the displays rather than by assignment afterwards — match whichever the file does; do not restructure it.

- [ ] **Step 2: Run — RED**

```bash
poetry run pytest -q tests/api/test_admin_signups.py
poetry run pytest -q tests/perf/test_query_plans.py -k signups
```

Expected: `ModuleNotFoundError: No module named 'app.api.admin_signups'` from the plan gate, and every API test failing `404` (JSON `{"detail": "Not Found"}` from `not_found_router`) because no route is mounted.

- [ ] **Step 3: Implement — `app/api/admin_signups.py`**

```python
"""The Admin "Launch sign-ups" surface (Task I5d, John 2026-09-08).

`interest_signup` is filled by the public Coming Soon page (`app/api/interest.py`, spec
2026-09-06 §3), whose own closing sentence is "No email is sent from here; the Identity wave's
Resend pipeline reads this table at launch". This module is the other end of that sentence: the
list staff read, the export they hand to whoever addresses the mail, and the one send.

Three shapes here are load-bearing, exactly as in `app/api/admin_users.py` beside it:

* **Every guard is a module-level constant, never wrapped.** `tests/auth/test_permissions.py`
  resolves a route's permission by the guard's object IDENTITY.
* **`audit.write(` is called in each audited endpoint's OWN body**, never through a helper: the
  drift test reads `inspect.getsource(route.endpoint)`.
* **`signups.read` LISTS and is not audited; `signups.export` and `signups.notify` are.** Same
  reasoning as `users.review` vs `users.view_detail` (I5 fix round 1, C2): a screen that polls the
  list must not write one row per poll into a table whose triggers refuse DELETE.

The keyset cursor helpers come from `admin_users` rather than being copied (D-I5d-11). F3 — a
cursor carrying only a timestamp, which dropped every row sharing the last row's `created_at` and
then reported the list complete — is exactly the defect a second copy would re-introduce, and
`now()` is transaction time, so ties are routine in this table too. `_keyset` raises
`admin_users.BadCursor` on anything that is not a `<timestamp>|<uuid>` pair, which is why that
class is not imported here: it is never referenced by name, only raised through the helper.
"""
from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.api.admin_users import _cursor, _iso, _keyset
from app.auth import audit
from app.auth import sessions as S
from app.auth.deps import AuthError, require
from app.db import sync_conn

router = APIRouter(prefix="/api/admin")

REQUIRE_SIGNUPS_READ = require("signups.read")
REQUIRE_SIGNUPS_EXPORT = require("signups.export")
REQUIRE_SIGNUPS_NOTIFY = require("signups.notify")

Exporter = Annotated[S.Principal, Depends(REQUIRE_SIGNUPS_EXPORT)]
Notifier = Annotated[S.Principal, Depends(REQUIRE_SIGNUPS_NOTIFY)]

MAX_LIST = 200
# At most this many rows leave in one file. The table is a launch-notification list, not an event
# stream; the cap is a floor under memory rather than a product limit (D-I5d-8).
MAX_EXPORT = 100_000
CSV_COLUMNS = ("id", "email", "source", "consent_version", "created_at", "launch_mailed_at")
# The characters a spreadsheet reads as the start of a formula. `app/api/interest.py`'s EMAIL_RE
# accepts an address beginning with any of the first four, so this is a value this table can hold.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class BadFilter(AuthError):
    """A `source=`/`consent_version=` value that names no row. Validated against the values the
    table actually holds, not a hard-coded enum (D-I5d-6): both columns are free `text`, so an enum
    would refuse a legitimate future source — while a 200 with an empty list would read as "no such
    sign-ups" instead of "no such filter" (the F10 defect, in this tab)."""

    status = 422
    code = "BAD_FILTER"

    def __init__(self, name: str, known: list[str]) -> None:
        self.message = f"{name} must be one of {', '.join(known) or '(no sign-ups yet)'}"
        super().__init__()


# One grouped scan answers three questions: the counts the tab shows, the count for the current
# filter, and (D-I5d-6) which filter values exist. Kept as one statement so those three can never
# disagree with each other.
COUNTS_SQL = """
SELECT source, consent_version, (launch_mailed_at IS NOT NULL) AS mailed, count(*)
  FROM interest_signup GROUP BY 1, 2, 3
"""

LIST_SQL = """
SELECT id, email, source, consent_version, created_at, launch_mailed_at
  FROM interest_signup
 WHERE (%(source)s::text IS NULL OR source = %(source)s)
   AND (%(consent_version)s::text IS NULL OR consent_version = %(consent_version)s)
   AND (%(cursor_at)s::timestamptz IS NULL
        OR (created_at, id) < (%(cursor_at)s::timestamptz, %(cursor_id)s::uuid))
 ORDER BY created_at DESC, id DESC
 LIMIT %(limit)s
"""


class Counts:
    """The grouped counts, read once and asked several questions.

    A small class rather than a tuple of dicts because the filter validation, the `filtered` count
    and the response body all read the same rows, and naming them here is what keeps the handler
    from re-deriving any of them differently."""

    def __init__(self, rows: list[tuple[str, str, bool, int]]) -> None:
        self.rows = rows
        self.total = sum(n for _s, _c, _m, n in rows)
        self.mailed = sum(n for _s, _c, m, n in rows if m)
        self.by_source: dict[str, int] = {}
        self.by_consent: dict[str, int] = {}
        for source, consent, _mailed, n in rows:
            self.by_source[source] = self.by_source.get(source, 0) + n
            self.by_consent[consent] = self.by_consent.get(consent, 0) + n

    def filtered(self, source: str | None, consent_version: str | None) -> int:
        return sum(n for s, c, _m, n in self.rows
                   if (source is None or s == source) and (consent_version is None or c == consent_version))

    def body(self, source: str | None, consent_version: str | None) -> dict[str, Any]:
        return {"total": self.total, "launch_mailed": self.mailed, "not_mailed": self.total - self.mailed,
                "filtered": self.filtered(source, consent_version),
                "by_source": dict(sorted(self.by_source.items())),
                "by_consent_version": dict(sorted(self.by_consent.items()))}


def _counts(cur: Any) -> Counts:
    cur.execute(COUNTS_SQL)
    return Counts(cast("list[tuple[str, str, bool, int]]", cur.fetchall()))


def _check_filters(counts: Counts, source: str | None, consent_version: str | None) -> None:
    """Both filters against the values the table holds (D-I5d-6). Raised BEFORE the list query, so
    a refused request costs one grouped scan and nothing else."""
    if source is not None and source not in counts.by_source:
        raise BadFilter("source", sorted(counts.by_source))
    if consent_version is not None and consent_version not in counts.by_consent:
        raise BadFilter("consent_version", sorted(counts.by_consent))


def _params(source: str | None, consent_version: str | None, cursor: str | None, limit: int) -> dict[str, Any]:
    keyset_at, keyset_id = _keyset(cursor)
    return {"source": source, "consent_version": consent_version,
            "cursor_at": keyset_at, "cursor_id": keyset_id, "limit": limit}


@router.get("/signups", dependencies=[Depends(REQUIRE_SIGNUPS_READ)])
async def list_signups(source: str | None = None, consent_version: str | None = None,
                       cursor: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Every launch-notification sign-up, newest first, with the counts the tab shows.

    NOT audited (`signups.read` is not in `AUDITED`): this is the read a screen polls, and one row
    per poll would fill an append-only table with reads of the list. The bulk export beside it is
    audited, because that is the act that takes the addresses somewhere else."""
    capped = min(max(limit, 1), MAX_LIST)
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        counts = _counts(cur)
        _check_filters(counts, source, consent_version)
        cur.execute(LIST_SQL, _params(source, consent_version, cursor, capped + 1))
        rows = cur.fetchall()
    items = [{"id": str(r[0]), "email": r[1], "source": r[2], "consent_version": r[3],
              "created_at": r[4].isoformat(), "launch_mailed_at": _iso(r[5])}
             for r in rows[:capped]]
    last = items[-1] if len(rows) > capped else None
    return {"items": items,
            "next_cursor": _cursor(cast("str", last["created_at"]), cast("str", last["id"])) if last is not None else None,
            "counts": counts.body(source, consent_version)}


def _safe(value: str) -> str:
    """`value`, with a leading formula character neutralised (D-I5d-7).

    A single apostrophe is what every spreadsheet reads as "the rest is text". The untransformed
    value is always one `GET /api/admin/signups` away; this file's audience is a spreadsheet."""
    return "'" + value if value.startswith(FORMULA_PREFIXES) else value


def _csv_rows(source: str | None, consent_version: str | None) -> Iterator[str]:
    """The file, one rendered line at a time.

    A SYNC generator on purpose: Starlette iterates one in a threadpool, so the blocking psycopg2
    reads below never run on the event loop. An ordinary client-side cursor, not a named one —
    `sync_conn()` is autocommit and psycopg2 refuses a server-side cursor outside a transaction
    (D-I5d-8 records the upgrade path). `closing(...)` inside the generator is what returns the
    connection to the pool when a client disconnects mid-file: the generator is closed, the
    `finally` runs."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)

    def flush() -> str:
        line = buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        return line

    writer.writerow(CSV_COLUMNS)
    yield flush()
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        cur.execute(LIST_SQL, _params(source, consent_version, None, MAX_EXPORT))
        for row in cur:
            writer.writerow([_safe(str(row[0])), _safe(row[1]), _safe(row[2]), _safe(row[3]),
                             row[4].isoformat(), _iso(row[5]) or ""])
            yield flush()


@router.get("/signups.csv")
def export_signups(request: Request, principal: Exporter,
                   source: str | None = None, consent_version: str | None = None) -> StreamingResponse:
    """The same list as a downloadable RFC 4180 file: CRLF, minimal quoting, doubled quotes, UTF-8
    and no BOM (D-I5d-7).

    A plain `def`, so FastAPI runs it in a threadpool like the generator it returns. The filters are
    validated and the audit row is written BEFORE the first byte leaves, so a client that
    disconnects mid-file still leaves the trace that the export was asked for."""
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            _check_filters(_counts(cur), source, consent_version)
        audit.write(conn, actor=principal, action="signups.export", target_type="interest_signup",
                    after={"source": source, "consent_version": consent_version}, request=request)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    return StreamingResponse(
        _csv_rows(source, consent_version),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="practice-match-signups-{stamp}.csv"'},
    )
```

In `app/main.py`, add the import beside the others and one `include_router` line **outside** the `site_mode == "app"` block, immediately before `app.include_router(interest_router)`:

```python
from app.api.admin_signups import router as admin_signups_router
```

```python
    # UNCONDITIONALLY, unlike `admin_users_router` above (Task I5d, D-I5d-5): `interest_signup` is
    # filled by the Coming Soon page, so the rows this reads only exist on PRODUCTION, which runs
    # `coming_soon` until launch. Gating it the same way would make the capability unreachable
    # exactly where the data is. Every route on it is `require(...)`-guarded, and the one action
    # that could do harm — the mail whose copy says the site is open — refuses with 409
    # NOT_LAUNCHED until `SITE_MODE=app`.
    app.include_router(admin_signups_router)
```

- [ ] **Step 4: Run — GREEN**

```bash
poetry run pytest -q tests/api/test_admin_signups.py
poetry run pytest -q tests/auth/test_permissions.py tests/auth/test_matrix.py    # the new routes are walked here
poetry run pytest -q tests/perf/test_query_plans.py -k signups
poetry run pytest -q tests/perf/test_api_latency.py -k signups
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
poetry run ruff check . && poetry run mypy --strict app scripts
```

Expected: green. Note what the guard tests now say without being edited: `test_every_route_is_guarded_or_public` sees three guarded routes; `test_audited_permissions_are_written_by_their_handlers` sees `audit.write(` in `export_signups`; `test_every_audited_action_is_named_after_a_permission` sees `"signups.export"`, which IS a permission; `tests/auth/test_matrix.py` gains the new rows automatically and asserts that a token principal is refused on the re-auth route in Task I5d.4.

If coverage is short, the likely gaps are `BadFilter`'s empty-table message branch, `_safe`'s untouched branch and `_csv_rows`' zero-row path — cover them with tests, never with a pragma.

- [ ] **Step 5: Commit**

```bash
git add app/api/admin_signups.py app/main.py tests/api/test_admin_signups.py \
        tests/perf/test_api_latency.py tests/perf/test_query_plans.py
git commit -m "$(cat <<'EOF'
feat(admin): read and export the Coming Soon launch sign-ups

Wave 2a Task I5d. GET /api/admin/signups is the keyset-paged list with the
counts the tab shows, filterable by source and consent version — the filter
values are validated against the rows that exist, not a hard-coded enum.
GET /api/admin/signups.csv streams the same list as RFC 4180 UTF-8 with a
header row and Content-Disposition: attachment; a leading formula character is
neutralised for spreadsheets and the raw value stays in the JSON list.

The router is mounted in both site modes: the rows only exist on production,
which runs coming_soon until launch. Both routes are permission-gated, the
export is audited, and the polled list deliberately is not.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
git push origin HEAD && git push production HEAD
```

---

### Task I5d.4: The launch mail — template, `POST /api/admin/signups/launch-mail`, runbook

*Standard-tier implementer. The write half: one message per sign-up, exactly once, through the existing outbox → Resend worker.*

**Files:**
- Modify: `app/mail/templates.py` (the `launch_announcement` entry, and the module docstring's count), `app/mail/outbox.py` (`TEMPLATES`), `app/api/admin_signups.py` (the endpoint), `docs/RUNBOOK-identity.md` (§12), `pyproject.toml` + `frontend/package.json` (one patch bump, in lockstep)
- Test: `tests/mail/test_templates.py`, `tests/mail/test_send.py`, `tests/api/test_admin_signups.py`

**Interfaces:**
- Consumes: `app.mail.outbox.enqueue(conn, to=, template=, params=, idempotency_key=) -> bool` (False when the key already exists), `app.mail.templates.render`, `app.mail.tasks.allowlisted` / `send_due` (unchanged), `settings.link_base_url`, `settings.site_mode`, `interest_signup.launch_mailed_at`.
- Produces:
  - Template key `launch_announcement`, `params=("link",)`.
  - `POST /api/admin/signups/launch-mail` body `{"dry_run": true}` → `200`
    ```json
    {"dry_run": true, "selected": 500, "queued": 0, "already_mailed": 0, "not_mailed": 1830, "remaining": 1830}
    ```
    with `{"dry_run": false}` → `queued` outbox rows written, `selected` rows stamped, `remaining` = `not_mailed - selected`. Refusals: `401`, `403` without `signups.notify`, `403 REAUTH_REQUIRED` from a stale session, `403 REAUTH_TOKEN` from any api token, `409 NOT_LAUNCHED` for a real send while `SITE_MODE != "app"`.
- Unchanged: `app/mail/tasks.py`, `app/mail/resend_client.py`, `app/api/webhooks.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/mail/test_templates.py — modify the count test, then append

def test_the_fifteen_keys_are_exactly_the_ones_the_outbox_accepts():
    """Was `test_the_fourteen_keys_…` until Task I5d added `launch_announcement`. Two lists, one
    truth: a key in one and not the other is either a row that can never be rendered or a template
    nothing can reach."""
    from app.mail.outbox import TEMPLATES as ACCEPTED

    assert set(TP.TEMPLATES) == set(ACCEPTED)
    assert len(TP.TEMPLATES) == 15


def test_the_launch_announcement_keeps_the_pages_promise_and_carries_a_link():
    """The Coming Soon page's promise is the specification for this mail: "One message, when it
    launches. Nothing else, and never shared." (`coming-soon/src/App.vue`) and "Leave your email
    and we'll write to you once — the day it opens." The mail has to be that one message and has
    to say so, or the promise was not kept."""
    r = TP.render("launch_announcement", {"link": "https://foundation.vin"}, base_url="https://foundation.vin")
    assert r.subject == "Practice Match is open"
    assert "token=" not in r.subject
    for part in (r.text, r.html):
        assert "the one message you asked for" in part
        assert "was not shared" in part
        assert "https://foundation.vin" in part
    assert "<img" not in r.html                       # spec §5: no tracking pixels, anywhere


def test_the_launch_announcement_promise_is_read_from_the_page_rather_than_retyped():
    """The page is the source of the promise, so the assertion reads it rather than repeating it —
    the same rule `design_status_body` follows for the gate-screen copy."""
    page = (Path(__file__).resolve().parents[2] / "coming-soon" / "src" / "App.vue").read_text()
    assert "One message, when it launches. Nothing else, and never shared." in page
```

```python
# tests/mail/test_send.py — append

def test_a_launch_announcement_row_is_suppressed_outside_production_unless_allowlisted(conn, monkeypatch):
    """`EMAIL_ALLOWLIST` is a fail-CLOSED gate and Task I5d changes nothing about it: on QA an
    empty allowlist sends to nobody, and a refused row is recorded `suppressed` with the reason
    that says it was the environment and not the address."""
    monkeypatch.setattr(settings, "environment", "qa")
    monkeypatch.setattr(settings, "email_allowlist", "")
    monkeypatch.setattr(settings, "resend_api_key", "re_test")
    OB.enqueue(conn, to="someone@x.test", template="launch_announcement",
               params={"link": "https://qa.foundation.vin"}, idempotency_key="k:launch_announcement:1")
    assert tasks.send_due() == {"sent": 0, "suppressed": 1, "failed": 0, "retried": 0}
    with conn.cursor() as cur:
        cur.execute("SELECT status, last_error FROM email_outbox WHERE idempotency_key = 'k:launch_announcement:1'")
        assert cur.fetchone() == ("suppressed", tasks.REASON_NOT_ALLOWLISTED)
```

```python
# tests/api/test_admin_signups.py — append (add to the imports at the top of the file:
#   from datetime import timedelta
#   from app.auth import sessions as S
#   from app.auth import tokens as T
# )
LAUNCH = "/api/admin/signups/launch-mail"


@pytest.fixture
def admin_headers(member, conn, redis):
    """An admin whose session confirmed its password a moment ago — `signups.notify` is in REAUTH.

    The cache drop is not optional: `sessions.Principal` carries `reauth_at` and is cached for 60 s,
    so a bare UPDATE would leave `deps.require` reading the pre-update principal and answering
    `403 REAUTH_REQUIRED` to a session the test has just freshened."""
    account_id, cookies, headers = member(roles=("admin",))
    with conn.cursor() as cur:
        cur.execute("UPDATE session SET reauth_at = now() WHERE account_id = %s", (account_id,))
    S.invalidate_account(redis, account_id)
    return auth_headers(cookies, headers)


@pytest.fixture
def admin_token_headers(member, conn):
    """A bearer credential carrying `admin` — the containment case for D-I5d-2. Minted through
    `app.auth.tokens.issue_api_token` exactly as `tests/api/test_admin_users.py`'s token cases do;
    there is no shared fixture for it, so this is its own."""
    account_id, _cookies, _headers = member(roles=("admin",))
    issued = T.issue_api_token(conn, name="i5d-test", role="admin", created_by=account_id, ttl=timedelta(days=1))
    return {"Authorization": f"Bearer {issued.raw}"}


async def test_a_dry_run_counts_without_queuing_or_stamping_anything(client, conn, admin_headers):
    seed(conn, 4)
    r = await client.post(LAUNCH, json={"dry_run": True}, headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == {"dry_run": True, "selected": 4, "queued": 0, "already_mailed": 0,
                        "not_mailed": 4, "remaining": 4}
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM email_outbox")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM interest_signup WHERE launch_mailed_at IS NOT NULL")
        assert cur.fetchone()[0] == 0


async def test_dry_run_is_the_default_so_a_bodyless_call_sends_nothing(client, conn, admin_headers):
    seed(conn, 2)
    r = await client.post(LAUNCH, json={}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["dry_run"] is True and r.json()["queued"] == 0


async def test_a_real_send_queues_one_row_per_signup_and_stamps_each_one(client, conn, admin_headers):
    seed(conn, 3)
    r = await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    assert r.json() == {"dry_run": False, "selected": 3, "queued": 3, "already_mailed": 0,
                        "not_mailed": 3, "remaining": 0}
    with conn.cursor() as cur:
        cur.execute("SELECT to_email, template, params, idempotency_key FROM email_outbox ORDER BY id")
        rows = cur.fetchall()
        cur.execute("SELECT count(*) FROM interest_signup WHERE launch_mailed_at IS NULL")
        assert cur.fetchone()[0] == 0
    assert {r[1] for r in rows} == {"launch_announcement"}
    assert sorted(r[0] for r in rows) == ["S0@x.test", "S1@x.test", "S2@x.test"]
    assert all(r[2] == {"link": settings.link_base_url} for r in rows)
    assert all(r[3].endswith(":launch_announcement:1") for r in rows)


async def test_sending_twice_mails_nobody_twice(client, conn, admin_headers):
    """The whole point of `launch_mailed_at` (D-I5d-4). The outbox's own unique key cannot carry
    this: `purge_outbox` deletes delivered rows 24 hours after they are sent, so the second call
    would find no conflict."""
    seed(conn, 3)
    await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM email_outbox")            # the day after: purge_outbox has run
    second = await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    assert second.json() == {"dry_run": False, "selected": 0, "queued": 0, "already_mailed": 3,
                             "not_mailed": 0, "remaining": 0}
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM email_outbox")
        assert cur.fetchone()[0] == 0


async def test_a_signup_added_after_the_send_still_gets_the_message(client, conn, admin_headers):
    seed(conn, 2)
    await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    seed(conn, 1, prefix="L")                              # someone signs up an hour after launch
    r = await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    assert r.json()["queued"] == 1 and r.json()["already_mailed"] == 2


async def test_the_batch_is_capped_and_remaining_says_how_many_are_left(client, conn, admin_headers, monkeypatch):
    from app.api import admin_signups as AS

    monkeypatch.setattr(AS, "MAX_LAUNCH_BATCH", 2)
    seed(conn, 5)
    r = await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    assert r.json()["selected"] == 2 and r.json()["queued"] == 2 and r.json()["remaining"] == 3


async def test_the_launch_mail_is_refused_while_the_site_is_still_coming_soon(client, conn, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "site_mode", "coming_soon")
    seed(conn, 2)
    r = await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_LAUNCHED"
    # ...and the dry run still answers, which is the point of D-I5d-5: the count is readable on
    # production before the flip, the message is not sendable.
    dry = await client.post(LAUNCH, json={"dry_run": True}, headers=admin_headers)
    assert dry.status_code == 200 and dry.json()["not_mailed"] == 2


async def test_the_launch_mail_needs_signups_notify_and_a_fresh_password(client, conn, member, staff_headers):
    seed(conn, 1)
    assert (await client.post(LAUNCH, json={"dry_run": True}, headers=staff_headers)).status_code == 403
    _, cookies, headers = member(roles=("admin",))                 # never re-authenticated
    r = await client.post(LAUNCH, json={"dry_run": True}, headers=auth_headers(cookies, headers))
    assert r.status_code == 403 and r.json()["error"]["code"] == "REAUTH_REQUIRED"


async def test_the_send_writes_one_audit_row_naming_the_counts(client, conn, admin_headers):
    seed(conn, 2)
    await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    with conn.cursor() as cur:
        cur.execute("SELECT action, target_type, after, reason FROM audit_log WHERE action = 'signups.notify'")
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "signups.notify" and rows[0][1] == "interest_signup"
    assert rows[0][2] == {"selected": 2, "queued": 2, "already_mailed": 0, "not_mailed": 2}
    assert rows[0][3] == "send"


async def test_a_dry_run_is_audited_too_and_says_so(client, conn, admin_headers):
    seed(conn, 2)
    await client.post(LAUNCH, json={"dry_run": True}, headers=admin_headers)
    with conn.cursor() as cur:
        cur.execute("SELECT reason, after FROM audit_log WHERE action = 'signups.notify'")
        reason, after = cur.fetchone()
    assert reason == "dry_run" and after["queued"] == 0


async def test_nothing_here_talks_to_resend(client, conn, admin_headers):
    """Spec §5: never a network call on the request path. The endpoint writes an outbox row and
    returns; the Celery `mail.send` task is the only thing in the codebase that opens an HTTP
    client. Asserted on the module's SOURCE — it must import neither the Resend client nor httpx —
    and on the row it leaves, which is `queued` with no provider id."""
    import app.api.admin_signups as AS

    source = inspect.getsource(AS)
    assert "resend_client" not in source and "import httpx" not in source
    seed(conn, 1)
    await client.post(LAUNCH, json={"dry_run": False}, headers=admin_headers)
    with conn.cursor() as cur:
        cur.execute("SELECT status, provider_id FROM email_outbox")
        assert cur.fetchone() == ("queued", None)
```

Also add, to `tests/api/test_admin_signups.py`, the api-token containment case (it is the reason `signups.notify` is in `REAUTH`; `tests/auth/test_matrix.py` proves it generically, and this proves it over HTTP):

```python
async def test_no_api_token_can_ever_send_the_launch_mail(client, conn, admin_token_headers):
    """D-I5d-2. A leaked `admin` api token must not be able to mail the whole launch list. It has
    no password to confirm, so the re-auth gate is permanent, and the refusal says which of the two
    it is rather than the generic 403."""
    seed(conn, 1)
    r = await client.post(LAUNCH, json={"dry_run": False}, headers=admin_token_headers)
    assert r.status_code == 403 and r.json()["error"]["code"] == "REAUTH_TOKEN"
```

> `admin_token_headers` mints an `api_token` through `app.auth.tokens.issue_api_token` exactly as `tests/api/test_admin_users.py` already does for its token cases; reuse that fixture's shape rather than inventing a second one.

- [ ] **Step 2: Run — RED**

```bash
poetry run pytest -q tests/mail/test_templates.py -k "fifteen or launch"
poetry run pytest -q tests/api/test_admin_signups.py -k launch
```

Expected: `KeyError: 'launch_announcement'` from `TP.TEMPLATES[key]` and `assert 14 == 15`; every `launch-mail` test `404`.

- [ ] **Step 3: Implement**

`app/mail/outbox.py` — add the key to `TEMPLATES` and one sentence to the comment above it:

```python
TEMPLATES = frozenset({
    "verify_email", "account_exists", "application_received", "application_approved", "application_declined",
    "application_info_requested", "seller_application_received", "seller_application_approved",
    "seller_application_declined", "password_reset", "password_changed", "signin_new_device",
    "account_suspended", "account_revoked",
    # The fifteenth (Task I5d): the ONE message the Coming Soon page promised its sign-ups. Not
    # transactional — nobody did anything to cause it — which is why it is sent from an admin
    # action, once per address, and never again (`interest_signup.launch_mailed_at`).
    "launch_announcement",
})
```

`app/mail/templates.py` — change the module docstring's opening line to *"The fifteen email templates (spec §5): fourteen transactional, plus the one-off `launch_announcement` the Coming Soon page promised (Task I5d)."* and add the entry after `account_revoked`:

```python
    # Task I5d (John, 2026-09-08). The Coming Soon page's own promise is the specification:
    # "One message, when it launches. Nothing else, and never shared." and "Leave your email and
    # we'll write to you once — the day it opens." (`coming-soon/src/App.vue`). So the mail says it
    # is that message, and says the address was not shared — anything less would not be the promise
    # being kept. There is no list to leave, so there is no unsubscribe link: this is the only
    # message that will ever be sent to it.
    #
    # >>> COPY FOR JOHN'S APPROVAL <<< The page deliberately never says WHAT is coming (its "It's
    # for" line is redacted by design), so the second paragraph — the one sentence that introduces
    # Practice Match — has no source in any approved artefact and is written here to be replaced by
    # the VIN Foundation's own words. Everything else is the page's promise, echoed.
    "launch_announcement": Template(
        subject="Practice Match is open",
        text="Practice Match is open.\n\n"
             "You asked the VIN Foundation to write to you the day it opened. This is the one message you asked for.\n\n"
             "Practice Match is where veterinarians can look at practices for sale, see what a community's numbers "
             "actually say about them, and talk to the owners directly. It is built and run by the VIN Foundation.\n\n"
             "{link}\n\n"
             "Your address was not shared with anyone, and this is the only message this list will ever send you.",
        html=_p("Practice Match is open.")
             + _p("You asked the VIN Foundation to write to you the day it opened. This is the one message you asked for.")
             + _p("Practice Match is where veterinarians can look at practices for sale, see what a community's numbers "
                  "actually say about them, and talk to the owners directly. It is built and run by the VIN Foundation.")
             + _link_block("Open Practice Match")
             + _p("Your address was not shared with anyone, and this is the only message this list will ever send you.", QUIET),
        params=("link",),
    ),
```

`app/api/admin_signups.py` — add the three imports this half needs (they are deliberately **not** in Task I5d.3's version of the file: an import that nothing uses yet is a `ruff` F401 and would have failed that task's gate):

```python
from pydantic import BaseModel

from app.config import settings
from app.mail.outbox import enqueue
```

...then the refusal, the constants, the request model and the endpoint:

```python
class SiteNotLaunched(AuthError):
    """The launch mail, attempted while the site is still serving the Coming Soon page (D-I5d-5).

    Not a permission problem — the caller may well be an admin — so it is a 409 about the world,
    not a 403 about them. The message the mail carries says Practice Match is open; sending it
    before `SITE_MODE=app` would make the VIN Foundation's one promised message a false one."""

    status = 409
    code = "NOT_LAUNCHED"
    message = "The launch email cannot be sent while the site is in coming-soon mode."


LAUNCH_TEMPLATE = "launch_announcement"
# One call acts on at most this many rows (D-I5d-9): the handler holds one pooled connection for
# the length of its transaction, and an unbounded call would write tens of thousands of outbox rows
# under it. `remaining` in the response is how the caller knows to call again.
MAX_LAUNCH_BATCH = 500

LAUNCH_COUNTS_SQL = """
SELECT count(*) FILTER (WHERE launch_mailed_at IS NOT NULL),
       count(*) FILTER (WHERE launch_mailed_at IS NULL)
  FROM interest_signup
"""
# `FOR UPDATE`, not `SKIP LOCKED`: two admins clicking Send at the same moment must not each mail
# half the list. The second caller blocks on the first's rows, and READ COMMITTED re-evaluates the
# WHERE after the lock is granted — so once the first transaction commits, those rows have a
# `launch_mailed_at` and drop out of the second caller's result entirely.
UNMAILED_SQL = "SELECT id, email FROM interest_signup WHERE launch_mailed_at IS NULL ORDER BY id LIMIT %s FOR UPDATE"


class LaunchMailIn(BaseModel):
    # Defaults to a dry run (D-I5d-10): the caller has to say `false` out loud to send something
    # that cannot be unsent.
    dry_run: bool = True


@router.post("/signups/launch-mail")
async def launch_mail(body: LaunchMailIn, request: Request, principal: Notifier) -> dict[str, Any]:
    """Queues the launch announcement for every sign-up that has not had it — at most
    `MAX_LAUNCH_BATCH` per call — or, on a dry run, counts them and writes nothing.

    Exactly once, and it survives a crash: the `enqueue` and the `launch_mailed_at` stamp commit in
    the SAME transaction, so there is no state in which a row is marked mailed without its outbox
    row, or has two. The outbox's own idempotency key is a second belt but not the braces
    (D-I5d-4): `purge_outbox` deletes delivered rows a day later, so the key is gone by the time a
    careless second call could do damage.

    `signups.notify` is in REAUTH, so the caller has confirmed their password within ten minutes
    and no api token can reach this at all (`deps.TokenCannotReauth`) — which is the containment
    that keeps a leaked automation credential away from the VIN Foundation's whole launch list.

    Nothing here talks to Resend. The Celery `mail.send` task drains the outbox, applies
    `EMAIL_ALLOWLIST` outside production and refuses suppressed addresses, all unchanged."""
    if not body.dry_run and settings.site_mode != "app":
        raise SiteNotLaunched
    queued = 0
    with closing(sync_conn()) as conn, conn:
        with conn.cursor() as cur:
            cur.execute(LAUNCH_COUNTS_SQL)
            already, pending = cast("tuple[int, int]", cur.fetchone())
            batch: list[tuple[Any, str]] = []
            if not body.dry_run:
                cur.execute(UNMAILED_SQL, (MAX_LAUNCH_BATCH,))
                batch = cast("list[tuple[Any, str]]", cur.fetchall())
        for signup_id, email in batch:
            # `enqueue` returns False when the key is already there — count what was really
            # written, so the response cannot claim a row it did not create.
            if enqueue(conn, to=email, template=LAUNCH_TEMPLATE, params={"link": settings.link_base_url},
                       idempotency_key=f"{signup_id}:{LAUNCH_TEMPLATE}:1"):
                queued += 1
        if batch:
            with conn.cursor() as cur:
                cur.execute("UPDATE interest_signup SET launch_mailed_at = now() WHERE id = ANY(%s)",
                            ([signup_id for signup_id, _email in batch],))
        selected = len(batch) if not body.dry_run else min(pending, MAX_LAUNCH_BATCH)
        # In this handler's own body, never through a helper: the audit drift test reads
        # `inspect.getsource(route.endpoint)`. A dry run is audited too — rehearsing a mass mail is
        # worth a line — and `reason` is what tells the two apart.
        audit.write(conn, actor=principal, action="signups.notify", target_type="interest_signup",
                    after={"selected": selected, "queued": queued, "already_mailed": already, "not_mailed": pending},
                    reason="dry_run" if body.dry_run else "send", request=request)
    return {"dry_run": body.dry_run, "selected": selected, "queued": queued,
            "already_mailed": already, "not_mailed": pending,
            "remaining": pending - len(batch)}
```

- [ ] **Step 4: Docs — `docs/RUNBOOK-identity.md` §12**

Append a section. Every endpoint is written in backticks as a route TEMPLATE with no query string, because `tests/test_docs.py::test_identity_runbook_endpoints_exist` walks it against the live route table.

```markdown
## 12. The launch email

The Coming Soon page collects one thing: an address, and a promise — *"One message, when it
launches. Nothing else, and never shared."* This is how that message is sent, once.

**Before the flip.** `GET /api/admin/signups` reads the list (staff or admin) and
`GET /api/admin/signups.csv` downloads it. `POST /api/admin/signups/launch-mail` with
`{"dry_run": true}` answers with the counts and writes nothing; on production, while the site is
still in coming-soon mode, that is all it will do — a real send is refused with `409 NOT_LAUNCHED`,
because the message says Practice Match is open.

**The order at launch.**
1. Set production `SITE_MODE=app` in Railway (after `railway status` prints **Project: Practice
   Match**) and `scripts/deploy.sh production`; `scripts/verify-deploy.sh production` must report
   `site_mode: "app"`.
2. Sign in as an admin and confirm your password (`POST /api/auth/reauth`) — `signups.notify` is a
   re-authenticated action and no api token can ever satisfy it.
3. `POST /api/admin/signups/launch-mail` with `{"dry_run": true}`. Read `not_mailed`. That is how
   many people are about to hear from the VIN Foundation.
4. `POST /api/admin/signups/launch-mail` with `{"dry_run": false}`. It queues at most 500 per call
   and answers with `remaining`; repeat until `remaining` is 0.
5. Watch the outbox drain. The worker's `mail.send` runs every minute and takes 25 rows a batch, so
   a list of 1,500 takes about an hour. Nothing is lost if the worker restarts: a claimed row's
   lease expires and it is picked up again, and the provider's idempotency key stops that becoming
   a second delivery.

**Sending it twice is safe.** Each sign-up carries `launch_mailed_at`; a row that has it is never
selected again. A person who signs up after the send is picked up by the next call and gets the
same message — which is right: they were promised it too.

**On QA nothing leaves.** `EMAIL_ALLOWLIST` is fail-closed outside production: an address that is
not on it is recorded `suppressed` with the reason, and an empty allowlist sends to nobody. A QA
rehearsal therefore still stamps `launch_mailed_at`, so rehearse on QA data, never against a copy
of the production list.
```

- [ ] **Step 5: Run — GREEN, and the whole gate**

```bash
poetry run pytest -q tests/mail/ tests/api/test_admin_signups.py
poetry run pytest -q tests/test_docs.py -k "runbook or identity"
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
poetry run ruff check . && poetry run mypy --strict app scripts
cd frontend && npm run typecheck && npm test && npm run build && cd ..
```

Bump the version once, in lockstep, before committing:

```bash
python - <<'PY'
import json, pathlib, re
pkg = pathlib.Path("frontend/package.json"); text = pkg.read_text()
current = json.loads(text)["version"]
major, minor, patch = current.split("."); nxt = f"{major}.{minor}.{int(patch) + 1}"
# A regex on the version LINE, not a json round-trip: re-serialising package.json would reformat
# the whole file and the diff would stop being surgical.
pkg.write_text(re.sub(rf'"version": "{re.escape(current)}"', f'"version": "{nxt}"', text, count=1))
pp = pathlib.Path("pyproject.toml")
pp.write_text(re.sub(r'^version = "[^"]+"', f'version = "{nxt}"', pp.read_text(), count=1, flags=re.M))
print(current, "->", nxt)
PY
git diff --stat frontend/package.json pyproject.toml     # expect: 1 line changed in each
poetry run pytest -q tests/test_versions.py
```

- [ ] **Step 6: Commit**

```bash
git add app/mail/templates.py app/mail/outbox.py app/api/admin_signups.py \
        tests/mail/test_templates.py tests/mail/test_send.py tests/api/test_admin_signups.py \
        docs/RUNBOOK-identity.md pyproject.toml frontend/package.json
git commit -m "$(cat <<'EOF'
feat(admin): send the Coming Soon launch email, once per sign-up

Wave 2a Task I5d. POST /api/admin/signups/launch-mail queues the
launch_announcement template through the existing outbox -> Resend worker,
at most 500 rows a call, and stamps interest_signup.launch_mailed_at in the
same transaction — so a crash can neither mail twice nor lose a row. dry_run
defaults to true and returns the counts without writing anything.

Admin-only and re-authenticated, which also means no api token can ever send
it. Refused with 409 NOT_LAUNCHED while the site is still coming-soon: the
message says Practice Match is open.

The second paragraph of the mail copy is marked for John's approval — the
Coming Soon page deliberately never says what is coming, so it has no source
in an approved artefact.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
git push origin HEAD && git push production HEAD
```

- [ ] **Step 7: Verify on QA, then production**

The full gate, all four (CLAUDE.md):

1. `poetry run pytest` + `cd frontend && npm run typecheck && npm test && npm run build` — done in Step 5.
2. `npm run test:visual:baselines` then `npm run test:e2e` — **no screen changed**, so this proves zero regression rather than a new state. Any pixel that moves here is a bug in this task, not a new baseline.
3. `scripts/deploy.sh QA`, then on `https://qa.foundation.vin`: sign in as an admin, `POST /api/auth/reauth`, dry-run the launch mail, send it, and confirm the outbox rows are `suppressed` for every address not on QA's `EMAIL_ALLOWLIST`. Download the CSV and open it in a spreadsheet.
4. `scripts/deploy.sh production` and `scripts/verify-deploy.sh production`. **Production stays in coming-soon mode**, so the post-deploy check here is that the site is unchanged and that `POST /api/admin/signups/launch-mail` with `{"dry_run": false}` answers `409 NOT_LAUNCHED`. The launch mail itself is sent later, from the runbook's §12 order, on John's word.

---

### Task I5d.5: **GATED ON REV 3** — the Admin "Launch sign-ups" tab

> ## ⛔ DO NOT START THIS TASK
>
> **The gate:** do not start until the Rev 3 design for this tab is in `docs/design-reference/` — a
> `.dc.html` bundle (or an amendment to the V3 bundle) that shows the Launch sign-ups tab. The
> approved design `Practice Match V3.dc.html` has four admin tabs — Users, Listings, Requests, Data
> Sources — and no fifth. There is no Launch sign-ups screen to port.
>
> **Until it exists:** the capability is reachable by API and not by UI. Say exactly that in the
> hand-back; do not build a placeholder, a temporary table, a "TODO Phase 2" banner, or a fifth tab
> assembled from the other four. CLAUDE.md: *"Reference open first, port verbatim, absent beats
> faked."* The design request John hands the designer is
> `docs/design-reference/requests/2026-09-08-rev3-admin-launch-signups-tab.md`, written with this
> plan.
>
> **When it arrives**, this task is not "write a screen". It is: compose the amended design from the
> pristine bundle by **ruled D15 amendments**, regenerate every oracle from that amended design, and
> make the app match it at zero pixels. The design is the input, never the output.

**Files (when unblocked):**
- Create: `frontend/src/admin/signups.ts` (+ `signups.test.ts`) — the pure mapping from the API payload to the design's own row shape, following `frontend/src/admin/users.ts`'s Map-engines M6 pattern exactly
- Modify: `frontend/src/logic.js` (the `adminVals()` tab set gains the ruled key), `frontend/tests/screens.ts` (the new oracle states), `frontend/tests/design-amendments.ts` + `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md` (the new amendment family and its rows), `frontend/tests/baseline-manifest.json` (regenerated, deliberately)

**Interfaces this UI consumes (frozen by Tasks I5d.3 and I5d.4 — the tab invents nothing):**

| Call | Answers | Used for |
|---|---|---|
| `GET /api/admin/signups?source=&consent_version=&cursor=&limit=` | `{items[], next_cursor, counts}` — `items[]` is `{id, email, source, consent_version, created_at, launch_mailed_at}`; `counts` is `{total, launch_mailed, not_mailed, filtered, by_source, by_consent_version}` | the table, the tab's count pill (`counts.total`), the two filter menus (`by_source` / `by_consent_version` keys), "Load more" (`next_cursor`) |
| `GET /api/admin/signups.csv?source=&consent_version=` | a downloaded file | the Export action |
| `POST /api/admin/signups/launch-mail {"dry_run": true}` | `{dry_run, selected, queued, already_mailed, not_mailed, remaining}` | the confirmation step's numbers |
| `POST /api/admin/signups/launch-mail {"dry_run": false}` | the same shape, `queued > 0` | the Send action; `remaining > 0` means call again |
| refusals | `403 REAUTH_REQUIRED` · `403 REAUTH_TOKEN` · `409 NOT_LAUNCHED` · `422 BAD_FILTER` · `422 BAD_CURSOR` | the states the design must show |

**The permission rules the tab must honour** (`can()` from `frontend/src/auth/permissions.ts`, which Task I5d.1 regenerated): the tab renders with `signups.read`; the Export action with `signups.export`; the Send action with `signups.notify` — and `signups.notify` is in `REAUTH`, so the client must route it through the existing re-auth prompt exactly as the Users tab's Revoke does.

- [ ] **Step 1: Confirm the gate is open**

```bash
ls docs/design-reference/                       # the Rev 3 package must be here
git log --oneline -5 -- docs/design-reference/  # and committed
```

If the Rev 3 tab design is not present, **stop and report the block**. Do not proceed.

- [ ] **Step 2: Diff the pristine bundle and write the amendment entries — RED first**

The mechanism is `docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md` and `frontend/tests/design-amendments.ts`: the pristine `Practice Match V3.rev2.dc.html` is never edited, the amended `Practice Match V3.dc.html` is `pristine + amendments`, and `frontend/tests/design-amendments.test.ts` proves that byte for byte, pinning the set both ways (count and ids). Today that is **seven families, 51 entries**. Adding this tab means:

1. A new family `A8`, one row per literal edit, each with the date, John's ruling and what changes — the same voice as A2–A7.
2. `frontend/tests/design-amendments.ts` gains the `A8.*` entries.
3. The count and the id set pinned by `design-amendments.test.ts` are updated **in the test first**, watched RED, then made green by the entries.

Write the test change and run it:

```bash
cd frontend && npx vitest run tests/design-amendments.test.ts
```

Expected RED: the pinned count and id set no longer match.

- [ ] **Step 3: Oracle states, on both targets**

`frontend/tests/screens.ts` is the 28 approved states. Each state this tab adds must be reachable **in the reference** (through `frontend/tests/reference-server.mjs`'s `?props=` injection, which is why `startScreen`/`startGate`/`me` stay declared) **and** in the app, or it cannot be an oracle. Add one entry per state the design shows — at minimum the tab at rest, and whatever the Rev 3 design draws for the confirmation and "already sent" states. Naming follows the existing `admin-*` convention (`admin-launch-signups`, …).

Then regenerate and run:

```bash
cd frontend && npm run test:visual:baselines && npm run test:e2e
```

`maxDiffPixels: 0`. A failure means the app is wrong, not the test.

- [ ] **Step 4: The mapping module and the app wiring**

`frontend/src/admin/signups.ts`, following `users.ts`: import `cell` and `A` from `./users` (they are ported verbatim from `logic.js`'s `adminVals()` and a test already compares them against that file's output — do not make a third copy), and export a pure `toSignupRows(payload)`. Vitest at 100 % lines/branches/functions/statements.

`frontend/src/logic.js` gains the tab exactly as the amendment rules it, and nothing else: no restructure, no per-screen split, inline styles stay inline.

- [ ] **Step 5: The whole gate, then QA, then production**

```bash
poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100
cd frontend && npm run typecheck && npm test && npm run build
npm run test:visual:baselines && npm run test:e2e
```

Then `scripts/deploy.sh QA`, click through the tab on `https://qa.foundation.vin`, then production and `scripts/verify-deploy.sh production`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/admin/signups.ts frontend/src/admin/signups.test.ts frontend/src/logic.js \
        frontend/tests/screens.ts frontend/tests/design-amendments.ts frontend/tests/design-amendments.test.ts \
        frontend/tests/baseline-manifest.json \
        docs/design-reference/design_handoff_practice_match_v3/LOCAL_AMENDMENTS.md
git commit -m "$(cat <<'EOF'
feat(admin): the Launch sign-ups tab, composed from the Rev 3 design

Wave 2a Task I5d.5. Ported from the Rev 3 design through the D15 ruled-amendment
mechanism (family A8): the pristine bundle is untouched, LOCAL_AMENDMENTS.md
carries one row per edit, and design-amendments.test.ts proves pristine +
amendments == the amended file byte for byte. Oracles regenerated from that
amended design; the new states are reachable in the reference and in the app,
at zero pixels.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
EOF
)"
git push origin HEAD && git push production HEAD
```

---

## Open questions for John (decided here with a default, reversible in one line)

1. **The mail's second paragraph.** The Coming Soon page never says what is coming — its "It's for" line is a redacted block by design — so the one sentence that introduces Practice Match has no source in any approved artefact. It is written in `app/mail/templates.py` marked **copy for John's approval** and is a one-line change. The subject line, `"Practice Match is open"`, is in the same position.
2. **Reading the production list before the launch flip (D-I5d-5).** The default mounts the router in both site modes, so on production today the list and the export are reachable by the legacy `API_SECRET_KEY` bearer — the only credential that resolves while the auth surface is switched off. The real send is refused until `SITE_MODE=app`. The alternative is to gate the whole router like `admin_users_router`, which is one line and costs the pre-launch count.
3. **Should an api token be able to export the list (D-I5d-3)?** Today it can, if an admin mints it a `staff`/`admin` token under re-auth; every export is audited. Adding `signups.export` to `permissions.TOKEN_DENIED` would end that. Not done, because widening `TOKEN_DENIED` is a policy change nobody asked for.
4. **The drain rate.** `mail.send` runs every minute and claims 25 rows (`outbox.DUE_LIMIT`), so 1,500 sign-ups take about an hour to leave and 5,000 take three and a half. That is fine for an announcement and is left alone, because `DUE_LIMIT` was sized against `LEASE_S` by an invariant (`tests/mail/test_send.py::test_the_lease_outlasts_the_worst_case_batch`) and raising one means re-deriving the other. Flagged so nobody is surprised watching the outbox.
5. **CAN-SPAM / commercial-mail footer.** The transactional templates carry no postal address and no unsubscribe link, which is right for them. This one is an announcement to a list, which is a different category in US law. The VIN Foundation should decide whether it needs a postal address and a "why you received this" line; the template has the second already ("You asked the VIN Foundation to write to you the day it opened"). Not a blocker for QA; worth settling before the production send.
6. **The CSV and Excel (D-I5d-7).** No BOM, so a strict parser reads the header correctly; Excel on Windows can mis-render a non-ASCII address. Emails are overwhelmingly ASCII, so the default is strictness. Adding a BOM is one line if John hits it.

---

## Self-review

- **Spec coverage.** Coming Soon spec §3's closing sentence ("the Identity wave's Resend pipeline reads this table for the launch notification") is Task I5d.4. Identity spec §4's matrix rules are Task I5d.1 and are enforced by the existing exhaustive tests without editing them. §5's pipeline is reused, not rebuilt: outbox idempotency, the retry ladder, `EMAIL_ALLOWLIST`, suppression and the webhook are all untouched, and Task I5d.4 adds a test that proves the new template goes through the allowlist gate. §8's budget table gains one row at 150 ms, beside the admin queue it sits with. Every new route is guarded, walked and — where it matters — audited.
- **Nothing in this plan is a placeholder.** Every test body and every implementation body is the code to write. The one deliberately unwritten thing is the Admin tab's markup, and it is unwritten because the design does not exist; Task I5d.5 says so at the top, in a box, and gives the API contracts it will consume so nobody has to guess them later.
- **Type consistency.** `interest_signup.id` is `uuid` and is rendered `str(...)` in both the JSON list and the CSV. `created_at` and `launch_mailed_at` are `timestamptz`; `created_at` is always `.isoformat()`, `launch_mailed_at` goes through `admin_users._iso` (`str | None`) and becomes `""` in the CSV. The cursor is the `"<created_at>|<id>"` string `admin_users._cursor` builds, ending in `Z` so a `+` cannot arrive back as a space. `counts` values are `int`; `by_source`/`by_consent_version` are `dict[str, int]`. `enqueue` returns `bool`, which is why `queued` can be smaller than `selected` and the response reports both.
- **Zero-regression surfaces named out loud.** `app/main.py` (one added line, outside the `site_mode` block), `app/mail/outbox.py::TEMPLATES` and `app/mail/templates.py::TEMPLATES` (one key each, and the paired count test that keeps them equal), `tests/perf/*` (two dict entries and one seed). `app/api/admin_users.py` is imported from and never modified. No screen changes until Task I5d.5, so the visual and DOM oracles are pure regression proof for Tasks I5d.1–I5d.4.
