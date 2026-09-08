#!/usr/bin/env python3
"""The personas the approved design's screenshots are taken as, and the ones the visual harness
reaches the gate screens with.

Three MEMBER accounts, all named Dr. Rachel Mendes of the StartUp Club, differing only in what they
are allowed to open — because since amendment A5.4 the account menu renders `/api/me`'s computed
`role`, so the account decides what the header says (A-I8.2 / D-I8-8):

    buyer@   role buyer            → "Approved buyer · StartUp Club"            the design's own fixture text
    seller@  roles buyer + seller  → "Approved buyer and seller · StartUp Club"  the seller dashboard and wizard
    design@  all four roles        → "VIN Foundation admin · StartUp Club"       the VIN Foundation Admin screens

`buyer@` is the oracle persona for the nineteen buyer-family states precisely because
`labels.role_label({"buyer"}, "StartUp Club")` reproduces the design's fixture string letter for
letter — John's rule for this wave is that the design's copy does not change, so the account is
chosen to fit the design rather than the other way round.

`design@practice-match.test` holds every role and carries a pre-approved buyer application, so a
reviewer can click through the whole marketplace on QA without first inventing a member. Idempotent:
run it as often as you like.

It also upserts `pending@`, `needs-review@` and `declined@practice-match.test` (D-I8-4, amendment
A-I8): the Playwright `app` project used to reach the "under review" and "not granted" gates by
clicking the design's own "Prototype — access states" shortcuts, and amendment A6.2 takes those out
of the design, so the only honest way in is a real account in that state — `logic.js`'s A5.4
bootstrap maps `pending`/`needs_review` to the "under review" gate and `declined` to the "not
granted" one. Same password, same `.test` domain, same production refusal. `needs-review@` and
`declined@` each carry one real `application` row (Task S3), so the applicant answer/re-apply
screens have something to show.

Task S3 also seeds `unverified@`, `verified@` and `invited@practice-match.test` — one account per
state the sign-up/verify/reset/accept-invite screens start from — and twelve single-use
`email_token` fixture rows per purpose (`FIXTURE_TOKENS`), recreated every run for the visual
harness to consume through the real endpoints. A-S5.2 adds a TENTH account, `verify-me@`, purely to
own the verify tokens: consuming one flips its account to `verified` for good, and the oracle needs
`unverified@` to still be unverified after every capture.

TEN accounts in all: `design@`, `buyer@`, `seller@` (members); `pending@`, `needs-review@`,
`declined@` (applicants with a state to render); `unverified@`, `verify-me@`, `verified@`,
`invited@` (the identity screens).

    ENVIRONMENT=qa poetry run python scripts/seed_persona.py

Task S7 (John's ruling, 2026-09-08) makes idempotence a stronger promise: this script RESTORES.
Run over fixtures a full Playwright run has just mutated — verify, reset and invite tokens
consumed, `verify-me@` confirmed, `verified@`'s password rotated, `invited@` given one,
`needs-review@`'s application answered, a second row on `declined@`, and a live verify link the
resend endpoint minted for `unverified@` — it puts every one of them back exactly as a fresh seed
leaves them, so a remote run can begin from a known baseline and be repeated without any manual
step. Fix round 1 widened the restoration to the two things it first left: the fixtures' queued
`email_outbox` and `email_suppression` rows (undeliverable `.test` mail a real QA worker would
retry for ever) and the throwaway `e2e-…@example.org` accounts the live sign-up flow creates.
`tests/scripts/test_seed_persona_restores.py` proves it end to end and says what is still
deliberately NOT restored — sessions and the append-only audit log — and why.
`frontend/tests/global-setup.ts` runs this against the target before a `PW_APP_URL` run, and
`frontend/tests/global-teardown.ts` again after it, so a live QA run neither starts from nor leaves
a mutated fixture.

It **refuses on production, with no override flag** (exit 2). A fixture account with `admin` on the
stakeholders' real data is not something a `--yes` should be able to buy.

The password comes from `PERSONA_PASSWORD`, defaulting to the value below (documented in
`.env.example` / `DEPLOY.md`). Neither is ever printed — this script writes an Argon2id hash and
says nothing else about it.

The `app.*` imports are inside `main()` for the reason `scripts/bootstrap_admin.py` records:
`python scripts/seed_persona.py` puts `scripts/` on `sys.path`, not the repository root.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from collections.abc import Sequence
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

# Unconditionally, before the `app.*` imports inside `main()`: `python scripts/<this>.py` puts
# `scripts/` on sys.path, not the repository root. A duplicate entry costs nothing on a one-shot
# CLI, and the `if not in sys.path` guard it replaces was an arm no in-process test could take.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PERSONA_EMAIL = "design@practice-match.test"          # RFC 6761 `.test`: never deliverable, by design
PERSONA_NAME = "Dr. Rachel Mendes"
PERSONA_AFFILIATION = "StartUp Club"
PERSONA_ROLES = ("buyer", "seller", "staff", "admin")
DEFAULT_PASSWORD = "design-persona-quiet-lantern-42"
# A-I8.2 / D-I8-8: the two member personas whose labels the design's own header shows. Same name and
# affiliation as `design@` — only the grants differ, so `name` and `initials` are constant across the
# whole visual suite and only `role` varies with what the account may open.
ORACLE_PERSONAS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("buyer@practice-match.test", ("buyer",)),
    ("seller@practice-match.test", ("buyer", "seller")),
)
# D-I8-4: one row per gate state the harness has to reach. No role grants and no `application`
# row, deliberately: `can.effectiveRoles` makes any non-`active` account an `applicant` whatever it
# was granted, so a grant would buy these three nothing, and the design's status screens render
# their own fixture copy — Task I8b is what wires the real answer / re-apply screens to the API.
# The names are plainly fixture names; `labels.initials` renders them in the account menu.
STATE_PERSONAS: tuple[tuple[str, str, str], ...] = (
    ("pending@practice-match.test", "pending", "Pending Applicant"),
    ("needs-review@practice-match.test", "needs_review", "Applicant Under Review"),
    ("declined@practice-match.test", "declined", "Declined Applicant"),
)
PERSONA_APPLICATION = {
    "name": "Rachel Mendes, DVM",
    "vin_member_id": "",
    "school_year": "Texas A&M, 2014",
    "license_state": "TX",
    "employer": "Relief veterinarian",
    "intent": "Buy within 18 months.",
    "affirm": True,
}

# Task S3 (Wave 2a, I8b/I8c): the sign-up/verify/reset/accept-invite screens' oracle needs an
# account in each state those flows start FROM. `unverified@` and `verified@` share the documented
# persona password like every other fixture above; `invited@` does not — see INVITED_* below.
IDENTITY_STATE_PERSONAS: tuple[tuple[str, str, str], ...] = (
    ("unverified@practice-match.test", "unverified", "Unverified Applicant"),
    # A-S5.2 (S-1). `POST /api/auth/verify` is `UPDATE account SET state='verified' WHERE
    # state='unverified'`, so the FIRST fixture verify token a run consumes confirms its account
    # for good. The oracle's `gate-check-email` state and its "Send it again" flow both need an
    # account that is still `unverified` at every capture, and `dom.spec.ts` and `visual.spec.ts`
    # each drive the whole state list — so no test ordering can keep one account doing both jobs.
    # This account owns the verify tokens and nothing else: no state signs in as it, and burning it
    # costs nothing.
    ("verify-me@practice-match.test", "unverified", "Verify Fixture"),
    ("verified@practice-match.test", "verified", "Verified Applicant"),
)
VERIFY_FIXTURE_EMAIL = "verify-me@practice-match.test"
# A real Argon2id hash of a secret generated fresh and never stored anywhere but this hash — not
# `bootstrap_admin.py`'s `NO_PASSWORD` sentinel, because the point here is proving the *shared*
# persona password specifically does not open this account, and a sentinel can't verify against
# anything to prove that. The only way in is the `invite` fixture token seeded below.
INVITED_EMAIL = "invited@practice-match.test"
INVITED_STATE = "verified"
INVITED_NAME = "Invited Staff"

# D-I8-4 continued: `needs-review@` and `declined@` (STATE_PERSONAS above) get their first REAL
# `application` row, so the applicant's answer/re-apply screens (Task I8b) have something to
# render besides the design's own fixture copy. `pending@` still gets none — nothing in this wave
# reads a pending row's fields.
NEEDS_REVIEW_EMAIL = "needs-review@practice-match.test"
NEEDS_REVIEW_FIELDS = {
    "name": "Applicant Under Review, DVM",
    "vin_member_id": "",
    "school_year": "Colorado State, 2018",
    "license_state": "CO",
    "employer": "Associate veterinarian",
    "intent": "Buy within a year.",
    "affirm": True,
}
NEEDS_REVIEW_INFO_REQUEST = "Which practice do you work at now, and in what role?"
DECLINED_EMAIL = "declined@practice-match.test"
# Verbatim from the task brief.
DECLINED_FIELDS = {
    "name": "Declined Applicant, DVM",
    "school_year": "Texas A&M, 2012",
    "license_state": "TX",
    "employer": "Hill Country Veterinary Clinic",
    "intent": "Exploring ownership within two years.",
    "affirm": True,
}
DECLINED_DECISION_NOTE = "Employer is outside the marketplace's current pilot region."

# Twelve single-use tokens per purpose, recreated every run: Task S5's visual oracle consumes
# `fixture-<purpose>-01` … `-12` through the real endpoints instead of a live signup/forgot/invite
# flow, so a screenshot run never competes with itself for SIGNUP_EMAIL/FORGOT_EMAIL's daily
# budgets. The raw values are documented test constants the harness mirrors — never printed here
# beyond this pattern, and never a password.
FIXTURE_TOKEN_PREFIX = "fixture-"
FIXTURE_TOKEN_COUNT = 12
FIXTURE_TOKENS: dict[str, tuple[str, str]] = {
    "verify": (VERIFY_FIXTURE_EMAIL, "fixture-verify-{n:02d}"),
    "reset": ("verified@practice-match.test", "fixture-reset-{n:02d}"),
    "invite": (INVITED_EMAIL, "fixture-invite-{n:02d}"),
}
FIXTURE_TTL = {"verify": timedelta(hours=24), "reset": timedelta(hours=1), "invite": timedelta(days=7)}

# Task S7 fix round 1 (John's ruling, 2026-09-08). The live sign-up and forgot flows of
# `frontend/tests/account-flows.spec.ts` and the `gate-signin-reset-sent` state use a throwaway
# address per run and per take — `frontend/tests/harness.ts`'s `throwawayEmail` — and a sign-up
# creates a REAL account behind it. Nothing owned them, so on QA they accumulated one per run for
# ever. They are this script's to remove: the domain is RFC 2606 `example.org`, reserved and never
# a real user, and the local part is the harness's own `e2e-` prefix.
#
# Anchored at both ends, with a literal `@example.org`: a SQL `LIKE 'e2e-%@example.org'` would also
# match `e2e-x@evil.example.org`, which is somebody else's account at somebody else's domain. The
# harness holds the same string as `THROWAWAY_EMAIL_PATTERN` and `tests/test_docs.py` pins the two
# equal, so the shape the flows produce and the shape this deletes by cannot drift apart.
THROWAWAY_EMAIL_PATTERN = r"^e2e-[A-Za-z0-9._-]+@example\.org$"

# The ten addresses this script owns, in one place: the scope of the mail-row deletes below, and
# what `tests/scripts/test_seed_persona_restores.py` snapshots. Built from the same constants that
# seed them, so an eleventh fixture account cannot be owned by the upserts and not by the sweep.
FIXTURE_EMAILS: tuple[str, ...] = (
    PERSONA_EMAIL,
    *(email for email, _roles in ORACLE_PERSONAS),
    *(email for email, _state, _name in STATE_PERSONAS),
    *(email for email, _state, _name in IDENTITY_STATE_PERSONAS),
    INVITED_EMAIL,
)

# Review round 1, Minor 2: the delete-then-insert of application rows and fixture tokens below is
# idempotent SEQUENTIALLY, but not race-proof against two concurrent `seed_persona.py` runs — one
# run's DELETE interleaved with another's INSERT could raise a `token_hash` unique collision or
# leave a transient duplicate application row. `pg_advisory_xact_lock` takes this key for the
# lifetime of the surrounding transaction and releases it automatically at COMMIT/ROLLBACK, so a
# second run simply waits its turn rather than racing the first. The value is arbitrary — nothing
# else in this codebase takes an advisory lock, so no other key can collide with it.
SEED_LOCK_KEY = 0x5EEDF00D


def main(argv: Sequence[str] | None = None) -> int:
    from app.auth import audit
    from app.auth import passwords as P
    from app.auth import tokens as T
    from app.config import settings
    from app.db import sync_conn

    argparse.ArgumentParser(description="Seed the design persona account (never on production).").parse_args(argv)

    if settings.environment.lower() == "production":
        print("[seed_persona] refusing to run against production — this is a fixture account", file=sys.stderr)
        return 2

    # Hashed before the connection is opened: Argon2id is ~97 ms and nothing should hold a Postgres
    # backend idle-in-transaction across it (I4 fix round 1, Important 5).
    hashed = P.hash_password(os.environ.get("PERSONA_PASSWORD", DEFAULT_PASSWORD))
    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        # Review round 1, Minor 2: taken first, before any read or write below, so the whole run
        # is serialised against any other concurrent `seed_persona.py` run — see SEED_LOCK_KEY.
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (SEED_LOCK_KEY,))
        cur.execute("""INSERT INTO account (email, password_hash, state, display_name, affiliation_label)
                            VALUES (%s,%s,'active',%s,%s)
                       ON CONFLICT (email) DO UPDATE
                               SET password_hash=EXCLUDED.password_hash, state='active',
                                   display_name=EXCLUDED.display_name, affiliation_label=EXCLUDED.affiliation_label
                         RETURNING id""", (PERSONA_EMAIL, hashed, PERSONA_NAME, PERSONA_AFFILIATION))
        # INSERT ... ON CONFLICT DO UPDATE ... RETURNING always yields exactly one row.
        account_id = cast("tuple[UUID]", cur.fetchone())[0]
        # Task S7: every account this script owns, collected as it is upserted — the scope of the
        # `email_token` delete below. Built from the ids the upserts RETURN rather than from a
        # second query, so it can never name an account these ten emails do not.
        fixture_ids: list[UUID] = [account_id]
        for role in PERSONA_ROLES:
            cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                        (account_id, role, account_id))
        # `ON CONFLICT` cannot help here — `application` has no natural key — so the idempotency is
        # this: at most one approved buyer application per persona, however often the script runs.
        cur.execute("""INSERT INTO application (account_id, kind, fields, status, decided_by, decided_at)
                       SELECT %s, 'buyer', %s, 'approved', %s, now()
                        WHERE NOT EXISTS (SELECT 1 FROM application WHERE account_id=%s AND kind='buyer')""",
                    (account_id, json.dumps(PERSONA_APPLICATION), account_id, account_id))
        audit.write(conn, actor=None, action="persona.seed", target_type="account", target_id=account_id,
                    reason="seed_persona.py")
        for email, roles in ORACLE_PERSONAS:
            cur.execute("""INSERT INTO account (email, password_hash, state, display_name, affiliation_label)
                                VALUES (%s,%s,'active',%s,%s)
                           ON CONFLICT (email) DO UPDATE
                                   SET password_hash=EXCLUDED.password_hash, state='active',
                                       display_name=EXCLUDED.display_name, affiliation_label=EXCLUDED.affiliation_label
                             RETURNING id""", (email, hashed, PERSONA_NAME, PERSONA_AFFILIATION))
            oracle_id = cast("tuple[UUID]", cur.fetchone())[0]
            fixture_ids.append(oracle_id)
            for role in roles:
                cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                            (oracle_id, role, account_id))
            audit.write(conn, actor=None, action="persona.seed", target_type="account",
                        target_id=oracle_id, reason="seed_persona.py")
        state_persona_ids: dict[str, UUID] = {}
        for email, state, display_name in STATE_PERSONAS:
            cur.execute("""INSERT INTO account (email, password_hash, state, display_name)
                                VALUES (%s,%s,%s,%s)
                           ON CONFLICT (email) DO UPDATE
                                   SET password_hash=EXCLUDED.password_hash, state=EXCLUDED.state,
                                       display_name=EXCLUDED.display_name
                             RETURNING id""", (email, hashed, state, display_name))
            aid = cast("tuple[UUID]", cur.fetchone())[0]
            state_persona_ids[email] = aid
            fixture_ids.append(aid)
            audit.write(conn, actor=None, action="persona.seed", target_type="account",
                        target_id=aid, reason="seed_persona.py")

        # Task S3: the three identity-screen accounts. `unverified@`/`verified@` share `hashed`
        # like every fixture above; `invited@` gets a hash of a secret generated fresh THIS RUN and
        # kept nowhere — the invite token is the only way in.
        identity_ids: dict[str, UUID] = {}
        for email, state, display_name in IDENTITY_STATE_PERSONAS:
            cur.execute("""INSERT INTO account (email, password_hash, state, display_name)
                                VALUES (%s,%s,%s,%s)
                           ON CONFLICT (email) DO UPDATE
                                   SET password_hash=EXCLUDED.password_hash, state=EXCLUDED.state,
                                       display_name=EXCLUDED.display_name
                             RETURNING id""", (email, hashed, state, display_name))
            identity_ids[email] = cast("tuple[UUID]", cur.fetchone())[0]
            fixture_ids.append(identity_ids[email])
            audit.write(conn, actor=None, action="persona.seed", target_type="account",
                        target_id=identity_ids[email], reason="seed_persona.py")

        invited_hashed = P.hash_password(secrets.token_urlsafe(24))
        cur.execute("""INSERT INTO account (email, password_hash, state, display_name)
                            VALUES (%s,%s,%s,%s)
                       ON CONFLICT (email) DO UPDATE
                               SET password_hash=EXCLUDED.password_hash, state=EXCLUDED.state,
                                   display_name=EXCLUDED.display_name
                         RETURNING id""", (INVITED_EMAIL, invited_hashed, INVITED_STATE, INVITED_NAME))
        identity_ids[INVITED_EMAIL] = cast("tuple[UUID]", cur.fetchone())[0]
        fixture_ids.append(identity_ids[INVITED_EMAIL])
        audit.write(conn, actor=None, action="persona.seed", target_type="account",
                    target_id=identity_ids[INVITED_EMAIL], reason="seed_persona.py")

        # `needs-review@`'s and `declined@`'s first real application row — delete-then-insert, so
        # a re-run never accumulates a second row on either account (application has no natural
        # key `ON CONFLICT` could use). Scoped to `kind='buyer'` (review round 1, Minor 1): this
        # is the only kind seeded here, and a bare `account_id=%s` delete would erase any `seller`
        # application row a later task seeds on the same account, which this script does not own.
        needs_review_id = state_persona_ids[NEEDS_REVIEW_EMAIL]
        cur.execute("DELETE FROM application WHERE account_id=%s AND kind='buyer'", (needs_review_id,))
        cur.execute("""INSERT INTO application (account_id, kind, fields, status, decided_by, decided_at, info_request)
                       VALUES (%s, 'buyer', %s, 'needs_review', %s, now(), %s)""",
                    (needs_review_id, json.dumps(NEEDS_REVIEW_FIELDS), account_id, NEEDS_REVIEW_INFO_REQUEST))
        declined_id = state_persona_ids[DECLINED_EMAIL]
        cur.execute("DELETE FROM application WHERE account_id=%s AND kind='buyer'", (declined_id,))
        cur.execute("""INSERT INTO application (account_id, kind, fields, status, decided_by, decided_at, decision_note)
                       VALUES (%s, 'buyer', %s, 'declined', %s, now(), %s)""",
                    (declined_id, json.dumps(DECLINED_FIELDS), account_id, DECLINED_DECISION_NOTE))

        # Task S7 (John's ruling, 2026-09-08: "shared QA fixtures must not be left in a mutated
        # state after a live QA run"). Every `email_token` row on a fixture account goes, not only
        # the rows of the three (account, purpose) pairs seeded below — because the run ISSUES
        # tokens the seed never wrote: `POST /api/auth/verify/resend`, which `account-flows.spec.ts`
        # calls as `unverified@`, mints that account a live verify link, and `unverified@` owns no
        # fixture purpose at all, so nothing here reclaimed it. `tests/scripts/
        # test_seed_persona_restores.py` failed on exactly that one row, and only that one, before
        # this line existed; unbounded, it accumulated one live link per QA run.
        #
        # Scoped to the accounts this script owns, by email — `fixture_ids` holds the ids the ten
        # upserts above returned and nothing else, so no other account's token is ever in range.
        # An `email_token` row on a fixture account is by construction a test artefact: unlike the
        # `application` table (review round 1, Minor 1, whose `kind='buyer'` scoping stands), there
        # is no kind of row here that a later task could own on the same account.
        cur.execute("DELETE FROM email_token WHERE account_id = ANY(%s)", (fixture_ids,))

        # Twelve fresh single-use tokens per purpose. Deleted first so neither a used row from the
        # last run nor a stale one survives a re-seed — and deleted BY HASH as well (A-S5.2):
        # `email_token.token_hash` is globally unique and these twelve raw values are documented
        # constants, so when a purpose's owner changes — as `verify` did, from `unverified@` to
        # `verify-me@` — the previous owner's rows collide with the ones this run is about to
        # insert. A fresh database never sees it; every database seeded before the move does, and
        # the seed died on a `UniqueViolation` rather than reclaiming its own token. The by-hash
        # delete stays alongside the account-wide one above: a squatter need not be a fixture
        # account, and only this form reclaims a documented token from an arbitrary holder.
        for purpose, (email, pattern) in FIXTURE_TOKENS.items():
            target_id = identity_ids[email]
            hashes = [T.hash(pattern.format(n=n)) for n in range(1, FIXTURE_TOKEN_COUNT + 1)]
            cur.execute("DELETE FROM email_token WHERE token_hash = ANY(%s)", (hashes,))
            for raw_hash in hashes:
                cur.execute("""INSERT INTO email_token (account_id, purpose, token_hash, expires_at)
                               VALUES (%s,%s,%s, now() + %s::interval)""",
                            (target_id, purpose, raw_hash, FIXTURE_TTL[purpose]))

        # Task S7 fix round 1 (John's ruling, 2026-09-08), which overturns S7's first decision to
        # leave both of these alone.
        #
        # (a) MAIL. Every `email_outbox` row addressed to a fixture account, and every
        # `email_suppression` row against one. They are queued to `@practice-match.test` — RFC
        # 6761, which no mail server can accept — so they are test artefacts and not product
        # output, and on QA a real worker retries them for ever and can end up suppressing the
        # fixture addresses outright. Scoped by EXACT address (`= ANY(FIXTURE_EMAILS)`), never by a
        # pattern: nobody else's queued mail is in range, whatever it looks like.
        cur.execute("DELETE FROM email_outbox WHERE to_email = ANY(%s)", (list(FIXTURE_EMAILS),))
        cur.execute("DELETE FROM email_suppression WHERE email = ANY(%s)", (list(FIXTURE_EMAILS),))

        # (b) THROWAWAY SIGN-UPS. `POST /api/auth/signup` in the live flow creates a real account
        # at `e2e-<run>-<purpose>-<n>@example.org` on every run, and until now nothing owned it —
        # on QA they accumulated one per run, for ever. `THROWAWAY_EMAIL_PATTERN` is anchored at
        # both ends with a literal `@example.org`, so `e2e-x@evil.example.org` — which a SQL
        # `LIKE 'e2e-%@example.org'` would have taken — is out of range; a test plants exactly that
        # lookalike and requires it to survive. The account's `session`, `email_token`,
        # `application` and `role_grant` rows go with it through the schema's own ON DELETE
        # CASCADE; its `audit_log` rows stay, because that table is append-only by design and has
        # no foreign key to `account`.
        cur.execute("DELETE FROM email_outbox WHERE to_email ~ %s", (THROWAWAY_EMAIL_PATTERN,))
        cur.execute("DELETE FROM email_suppression WHERE email ~ %s", (THROWAWAY_EMAIL_PATTERN,))
        cur.execute("DELETE FROM account WHERE email ~ %s", (THROWAWAY_EMAIL_PATTERN,))
    print(f"[seed_persona] {PERSONA_EMAIL} is ready on {settings.environment} — roles: {', '.join(PERSONA_ROLES)}")
    oracles = ", ".join(f"{email} ({'+'.join(roles)})" for email, roles in ORACLE_PERSONAS)
    print(f"[seed_persona] oracle personas: {oracles}")
    print(f"[seed_persona] gate-state personas: {', '.join(f'{e} ({s})' for e, s, _ in STATE_PERSONAS)}")
    identity = ", ".join(f"{e} ({s})" for e, s, _ in IDENTITY_STATE_PERSONAS)
    print(f"[seed_persona] identity-screen personas: {identity}, {INVITED_EMAIL} ({INVITED_STATE}, invite-only sign-in)")
    print(f"[seed_persona] the verify fixture tokens belong to {VERIFY_FIXTURE_EMAIL}, so no other account is confirmed by a test")
    print(f"[seed_persona] fixture tokens: {FIXTURE_TOKEN_COUNT} per purpose ({', '.join(sorted(FIXTURE_TOKENS))}), recreated this run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
