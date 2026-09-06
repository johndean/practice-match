#!/usr/bin/env python3
"""The design persona — Dr. Rachel Mendes, the account the approved design's screenshots are of.

Upserts `design@practice-match.test` as an `active` account holding every role, with a pre-approved
buyer application behind it, so a reviewer can click through the whole marketplace on QA without
first inventing a member. Idempotent: run it as often as you like.

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
import sys
from collections.abc import Sequence
from contextlib import closing
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
PERSONA_APPLICATION = {
    "name": "Rachel Mendes, DVM",
    "vin_member_id": "",
    "school_year": "Texas A&M, 2014",
    "license_state": "TX",
    "employer": "Relief veterinarian",
    "intent": "Buy within 18 months.",
    "affirm": True,
}


def main(argv: Sequence[str] | None = None) -> int:
    from app.auth import audit
    from app.auth import passwords as P
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
    print(f"[seed_persona] {PERSONA_EMAIL} is ready on {settings.environment} — roles: {', '.join(PERSONA_ROLES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
