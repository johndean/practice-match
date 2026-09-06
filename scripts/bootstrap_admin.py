#!/usr/bin/env python3
"""The first admin.

Creates (or reactivates) an `active` account with the `admin` grant and NO usable password, then
prints a single-use 24 h invite link the person opens to set one. There is no default password and
none is ever printed: `NO_PASSWORD` is not an Argon2id hash, so `passwords.verify` can never
succeed against it, and the only way in is the link this prints —
`POST /api/auth/accept-invite` (`app/api/auth.py`), which applies the privileged password floor.

    ENVIRONMENT=qa poetry run python scripts/bootstrap_admin.py --email person@example.org

The address is a RUN-TIME argument on purpose. The VIN Foundation's four initial admins are not
named anywhere in this repository, and must not be.

Every run writes an audit row (`audit_log` is append-only by trigger) — `admin.bootstrap` when it
issues a link, `admin.bootstrap.refused` when it does not. Two refusals, each with its own exit
code so a wrapper can tell them apart:

* **2 — `ENVIRONMENT=production` without `--production`.** The same "say it out loud" shape as
  `scripts/deploy.sh`'s Railway-project guard, for the same reason: this machine speaks to more
  than one environment.
* **3 — the address already exists and is `suspended` or `revoked`, without `--reactivate`**
  (fix round 1, F8). `ON CONFLICT (email) DO UPDATE SET state='active'` applies to ANY existing
  address, so without this the script silently undid a suspension or revocation that has an audit
  trail behind it, granted that account `admin`, and printed a link that sets its password.

Issuing a link retires every unused `invite` token the account already has (fix round 1, F4) —
the statement `POST /api/auth/password/forgot` uses three files away, for the same reason: a link
printed to a terminal, a chat window or a CI log 23 hours ago must stop being a working
password-reset the moment a newer one is issued.

The `app.*` imports are inside `main()` deliberately: `python scripts/bootstrap_admin.py` puts
`scripts/` on `sys.path`, not the repository root, so the root has to be added first — and adding
it above a module-level import block is exactly the ordering ruff's E402 exists to stop.
"""
from __future__ import annotations

import argparse
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

INVITE_TTL = timedelta(hours=24)
# Never a valid Argon2id encoded hash, so nothing can ever verify against it. The account exists
# and holds `admin`; it simply has no password until the invite link is used.
NO_PASSWORD = "!invite-pending"
# States a bootstrap must not walk over silently: both are the recorded outcome of a staff decision.
BLOCKED_STATES = ("suspended", "revoked")


def main(argv: Sequence[str] | None = None) -> int:
    from app.auth import audit
    from app.auth import tokens as T
    from app.config import settings
    from app.db import sync_conn

    parser = argparse.ArgumentParser(description="Create the first admin and print a one-time invite link.")
    parser.add_argument("--email", required=True, help="the admin's email address (a run-time argument; never committed)")
    parser.add_argument("--production", action="store_true", help="required to run against ENVIRONMENT=production")
    parser.add_argument("--reactivate", action="store_true",
                        help="required when the address already exists and is suspended or revoked")
    args = parser.parse_args(argv)

    if settings.environment.lower() == "production" and not args.production:
        print("[bootstrap_admin] refusing to run against production without --production", file=sys.stderr)
        return 2

    with closing(sync_conn()) as conn, conn, conn.cursor() as cur:
        # Read and LOCK the existing row first: the refusal below must see the state a concurrent
        # decision left, and the upsert must not race it. `email` is citext, so this matches
        # whatever case the address was created with.
        cur.execute("SELECT id, state FROM account WHERE email=%s FOR UPDATE", (args.email,))
        existing = cur.fetchone()
        reactivating = existing is not None and existing[1] in BLOCKED_STATES
        if reactivating and not args.reactivate:
            # Audited either way: an attempt to bootstrap over a revoked account is exactly the
            # thing an auditor wants to see, whether or not it succeeded.
            audit.write(conn, actor=None, action="admin.bootstrap.refused", target_type="account",
                        target_id=cast("tuple[UUID, str]", existing)[0],
                        reason=f"account is {cast('tuple[UUID, str]', existing)[1]}; --reactivate not given")
            print(f"[bootstrap_admin] refusing: that address already exists and is "
                  f"{cast('tuple[UUID, str]', existing)[1]} — pass --reactivate to override", file=sys.stderr)
            return 3
        # `password_hash` is NOT overwritten on conflict: re-running this for an existing admin
        # issues them a fresh invite and leaves the password they already have working until they
        # use it.
        cur.execute("""INSERT INTO account (email, password_hash, state, display_name)
                            VALUES (%s,%s,'active',%s)
                       ON CONFLICT (email) DO UPDATE SET state='active'
                         RETURNING id""", (args.email, NO_PASSWORD, args.email.split("@")[0]))
        # INSERT ... ON CONFLICT DO UPDATE ... RETURNING always yields exactly one row.
        account_id = cast("tuple[UUID]", cur.fetchone())[0]
        cur.execute("INSERT INTO role_grant (account_id, role, granted_by) VALUES (%s,'admin',%s) ON CONFLICT DO NOTHING",
                    (account_id, account_id))
        # One live invite per account (F4), exactly as `password/forgot` keeps one live reset link.
        cur.execute("UPDATE email_token SET used_at = now() WHERE account_id=%s AND purpose='invite' AND used_at IS NULL",
                    (account_id,))
        token = T.issue_email_token(conn, account_id, "invite", INVITE_TTL)
        # `actor=None`: nobody is signed in — this is the credential that exists before any
        # credential does, which is precisely why it leaves a row.
        audit.write(conn, actor=None, action="admin.bootstrap", target_type="account", target_id=account_id,
                    reason="bootstrap_admin.py --reactivate" if reactivating else "bootstrap_admin.py")
    print(f"{settings.link_base_url}/accept-invite?token={token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
