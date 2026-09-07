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
harness to consume through the real endpoints.

    ENVIRONMENT=qa poetry run python scripts/seed_persona.py

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
    ("verified@practice-match.test", "verified", "Verified Applicant"),
)
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
    "verify": ("unverified@practice-match.test", "fixture-verify-{n:02d}"),
    "reset": ("verified@practice-match.test", "fixture-reset-{n:02d}"),
    "invite": (INVITED_EMAIL, "fixture-invite-{n:02d}"),
}
FIXTURE_TTL = {"verify": timedelta(hours=24), "reset": timedelta(hours=1), "invite": timedelta(days=7)}

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

        # Twelve fresh single-use tokens per purpose. Deleted first so neither a used row from the
        # last run nor a stale one survives a re-seed.
        for purpose, (email, pattern) in FIXTURE_TOKENS.items():
            target_id = identity_ids[email]
            cur.execute("DELETE FROM email_token WHERE account_id=%s AND purpose=%s", (target_id, purpose))
            for n in range(1, FIXTURE_TOKEN_COUNT + 1):
                raw = pattern.format(n=n)
                cur.execute("""INSERT INTO email_token (account_id, purpose, token_hash, expires_at)
                               VALUES (%s,%s,%s, now() + %s::interval)""",
                            (target_id, purpose, T.hash(raw), FIXTURE_TTL[purpose]))
    print(f"[seed_persona] {PERSONA_EMAIL} is ready on {settings.environment} — roles: {', '.join(PERSONA_ROLES)}")
    oracles = ", ".join(f"{email} ({'+'.join(roles)})" for email, roles in ORACLE_PERSONAS)
    print(f"[seed_persona] oracle personas: {oracles}")
    print(f"[seed_persona] gate-state personas: {', '.join(f'{e} ({s})' for e, s, _ in STATE_PERSONAS)}")
    identity = ", ".join(f"{e} ({s})" for e, s, _ in IDENTITY_STATE_PERSONAS)
    print(f"[seed_persona] identity-screen personas: {identity}, {INVITED_EMAIL} ({INVITED_STATE}, no usable password)")
    print(f"[seed_persona] fixture tokens: {FIXTURE_TOKEN_COUNT} per purpose ({', '.join(sorted(FIXTURE_TOKENS))}), recreated this run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
