"""Task S7 (John's ruling, 2026-09-08): "Before Task I10, add a deterministic test-fixture
reset/reseed mechanism so every DOM/visual run begins from a known baseline and can be repeated
without manual intervention" · "shared QA fixtures must not be left in a mutated state after a live
QA run".

`frontend/tests/global-setup.ts` is the mechanism — a remote (`PW_APP_URL`) run reseeds the target
before its first test, the same place a local run implicitly does through the `api` web server's
`migrate && reset_rate_limits && seed_persona` chain (A-I7, A-S5.1). This file is the PROOF that
reseeding is enough: that `scripts/seed_persona.py`, run a second time over fixtures a full
Playwright run has just mutated, puts every one of them back exactly as a fresh seed leaves them.

WHAT IS SNAPSHOTTED, and why those things
    accounts       `state`, the active `role_grant` roles, and WHICH known password opens the
                   account. Not the hash itself: Argon2id salts at random, so two seeds of the same
                   password never produce the same string — the fact that matters is which
                   credential works, which is also the fact the harness depends on.
    applications   every row on a fixture account, normalised to (kind, status, fields, flags,
                   decision_note, info_request, answer, answered?, resubmitted?). Not `id`,
                   `submitted_at` or `decided_at`: the seed deletes and re-inserts, so those move by
                   construction, and a stray row shows up in the row COUNT and content regardless.
    tokens         every `email_token` row on a fixture account, as (purpose, which documented
                   fixture token this is — or `not-a-fixture-token` — and whether it is used).
                   Twelve unused rows per purpose is the baseline the visual oracle spends.
    mail           every `email_outbox` row addressed to a fixture account, and every
                   `email_suppression` row against one. Fix round 1 (John's ruling, 2026-09-08)
                   OVERTURNS S7's first decision to leave them: they are queued to `.test`
                   addresses no mail server can accept, so they are test artefacts, not product
                   output — and on QA a real worker retries them for ever and can suppress the
                   fixture addresses. Scoped by exact address, never by pattern.
    throwaways     the accounts the live sign-up flow creates at
                   `e2e-<run>-<purpose>-<n>@example.org`. Also fix round 1: RFC 2606 reserved,
                   never a real user, one more per run for ever until the seed removed them.
                   Matched by the anchored `seed_persona.THROWAWAY_EMAIL_PATTERN`, which
                   `frontend/tests/harness.ts` mirrors and `tests/test_docs.py` pins equal.

DELIBERATELY OUT OF THE SNAPSHOT
    `session`      not a fixture: every run mints its own and the memo file is `PW_RUN_ID`-scoped
                   (`frontend/tests/global-setup.ts`), so a stale or revoked session cannot make a
                   later run non-deterministic. Deleting them would also sign a human reviewer's
                   live QA browser out in the middle of their click-through.
    `audit_log`    append-only by design (a DELETE trigger refuses); the seed writes ten of its
                   own rows every run, and a throwaway account's rows outlive the account — there
                   is no foreign key from `audit_log.actor_id`, deliberately.
    `last_sign_in_at`  a fact about the account's history that no screen, oracle or flow reads.
"""
from __future__ import annotations

import contextlib
import io
import json
from typing import Any

from app.auth import passwords as P
from app.auth import sessions as S
from app.auth import tokens as T
from scripts import seed_persona
from tests.api.conftest import ORIGIN, auth_headers, client  # noqa: F401  (`client` is a fixture, reused here)

# The three passwords a live run puts into the fixtures. `PERSONA_PW` is what the harness signs in
# with; the other two are what `POST /api/auth/password/reset` and `POST /api/auth/accept-invite`
# leave behind, and the whole point of the re-seed is that neither survives it. All three are
# documented test-only constants, exactly like `seed_persona.DEFAULT_PASSWORD`.
PERSONA_PW = "quiet-lantern-orbit-58"
RESET_FLOW_PW = "quiet-orbit-lantern-71"
INVITE_FLOW_PW = "quiet-orbit-lantern-72"
ANSWER = "I am an associate at Hill Country Veterinary Clinic and see small animals four days a week."
# The shape `frontend/tests/harness.ts`'s `throwawayEmail` produces, spelled out — RFC 2606
# `example.org`, never deliverable. `LOOKALIKE_EMAIL` is the trap: same local part, somebody else's
# domain, and the seed must leave it exactly where it is.
THROWAWAY_EMAIL = "e2e-0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0-signup-1@example.org"
LOOKALIKE_EMAIL = "e2e-0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0-signup-1@evil.example.org"

# One Argon2id verify is ~100 ms (64 MiB, t=3), so the snapshot tries only the passwords that could
# plausibly open each account rather than all three against all ten.
EXTRA_CANDIDATES = {
    seed_persona.INVITED_EMAIL: (("invite-flow", INVITE_FLOW_PW),),
    "verified@practice-match.test": (("reset-flow", RESET_FLOW_PW),),
}


def _fixture_emails() -> tuple[str, ...]:
    """Every account `scripts/seed_persona.py` owns — the script's OWN list (fix round 1: it is
    also the scope of the mail-row deletes, so the snapshot and the delete cannot disagree), built
    there from the same constants that seed them. The count is pinned below, so a new fixture
    account joins this snapshot deliberately rather than escaping it."""
    return seed_persona.FIXTURE_EMAILS


def _run_seed() -> None:
    """`main([])` in THIS process so pytest-cov sees the script's own lines (the pattern
    `tests/api/test_admin_users.py::_run_cli` uses); stdout is swallowed, never asserted on here."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = seed_persona.main([])
    assert code == 0, out.getvalue()


def _token_labels() -> dict[str, str]:
    """`token_hash` → the documented raw name, for the thirty-six fixture tokens."""
    return {
        T.hash(pattern.format(n=n)): f"{purpose}-{n:02d}"
        for purpose, (_email, pattern) in seed_persona.FIXTURE_TOKENS.items()
        for n in range(1, seed_persona.FIXTURE_TOKEN_COUNT + 1)
    }


def _opens(email: str, password_hash: str) -> tuple[str, ...]:
    candidates = (("persona", PERSONA_PW), *EXTRA_CANDIDATES.get(email, ()))
    return tuple(name for name, pw in candidates if P.verify(pw, password_hash))


def _snapshot(conn: Any) -> dict[str, Any]:
    emails = list(_fixture_emails())
    labels = _token_labels()
    with conn.cursor() as cur:
        cur.execute("SELECT email, state, password_hash FROM account WHERE email = ANY(%s) ORDER BY email", (emails,))
        accounts = {email: {"state": state, "password_opens": _opens(email, pw)} for email, state, pw in cur.fetchall()}

        cur.execute("""SELECT a.email, g.role FROM role_grant g JOIN account a ON a.id = g.account_id
                        WHERE a.email = ANY(%s) AND g.revoked_at IS NULL""", (emails,))
        roles: dict[str, list[str]] = {email: [] for email in accounts}
        for email, role in cur.fetchall():
            roles[email].append(role)
        for email, granted in roles.items():
            accounts[email]["roles"] = tuple(sorted(granted))

        cur.execute("""SELECT a.email, ap.kind, ap.status, ap.fields, ap.flags, ap.decision_note, ap.info_request,
                              ap.answer, ap.answered_at IS NOT NULL, ap.resubmitted_at IS NOT NULL
                         FROM application ap JOIN account a ON a.id = ap.account_id
                        WHERE a.email = ANY(%s)""", (emails,))
        applications: dict[str, list[tuple[Any, ...]]] = {email: [] for email in accounts}
        for email, kind, status, fields, app_flags, note, info, answer, answered, resubmitted in cur.fetchall():
            applications[email].append(
                (kind, status, json.dumps(fields, sort_keys=True), tuple(app_flags), note, info, answer, answered, resubmitted))

        cur.execute("""SELECT a.email, t.purpose, t.token_hash, t.used_at IS NOT NULL
                         FROM email_token t JOIN account a ON a.id = t.account_id
                        WHERE a.email = ANY(%s)""", (emails,))
        tokens: dict[str, list[tuple[Any, ...]]] = {email: [] for email in accounts}
        for email, purpose, token_hash, used in cur.fetchall():
            tokens[email].append((purpose, labels.get(token_hash, "not-a-fixture-token"), used))

        cur.execute("SELECT to_email, template, status FROM email_outbox WHERE to_email = ANY(%s)", (emails,))
        outbox = sorted(cur.fetchall())
        cur.execute("SELECT email, reason FROM email_suppression WHERE email = ANY(%s)", (emails,))
        suppressions = sorted(cur.fetchall())
        cur.execute("SELECT email FROM account WHERE email ~ %s", (seed_persona.THROWAWAY_EMAIL_PATTERN,))
        throwaways = sorted(row[0] for row in cur.fetchall())

    return {
        "accounts": accounts,
        "applications": {email: sorted(rows) for email, rows in applications.items()},
        "tokens": {email: sorted(rows) for email, rows in tokens.items()},
        "outbox": outbox,
        "suppressions": suppressions,
        "throwaways": throwaways,
    }


def _outbox_count(conn: Any) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM email_outbox WHERE to_email = ANY(%s)", (list(_fixture_emails()),))
        return int(cur.fetchone()[0])


def _session(conn: Any, redis_client: Any, email: str) -> tuple[Any, dict[str, str], dict[str, str]]:
    """A real session for a fixture account, minted exactly as `tests/api/conftest.py::member` does.

    Not `POST /api/auth/signin`: what a live run mutates is not the sign-in — it is the six calls
    below, each made through the real endpoint with a real principal. Signing in would add nothing
    to the snapshot but `last_sign_in_at`, which is deliberately outside it.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM account WHERE email=%s", (email,))
        account_id = cur.fetchone()[0]
    raw = S.create(conn, redis_client, account_id, "203.0.113.5", "pytest")
    return account_id, {"pm_session": raw, "pm_csrf": "csrf-1"}, {"X-CSRF-Token": "csrf-1", "Origin": ORIGIN}


async def _mutate_as_a_live_run_does(client, conn, redis) -> None:  # noqa: F811  (`client` the fixture, by name)
    """Everything `frontend/tests/account-flows.spec.ts`, `dom.spec.ts` and `visual.spec.ts` do to
    the fixtures on one live run — through the real endpoints, in the order a run makes them, and
    WITHOUT the reviewer-API restoration those specs perform (`decideAs`). S7 is the safety net
    beneath that restoration, so it has to be proved with the net alone."""
    # 0. A stranger signs up with the run's throwaway address (the live flow of
    #    `account-flows.spec.ts` §1): a real account, a verify token and an outbox row behind it.
    signup = await client.post("/api/auth/signup", json={"email": THROWAWAY_EMAIL, "password": PERSONA_PW})
    assert signup.status_code == 202, signup.text

    # 1. A verification link is consumed: `verify-me@` is confirmed for good, one verify token used.
    verify_token = seed_persona.FIXTURE_TOKENS["verify"][1].format(n=1)
    assert (await client.post("/api/auth/verify", json={"token": verify_token})).status_code == 200

    # 2. "Send it again" for `unverified@`, which issues that account a verify token of its own.
    _aid, cookies, hdr = _session(conn, redis, "unverified@practice-match.test")
    assert (await client.post("/api/auth/verify/resend", headers=auth_headers(cookies, hdr))).status_code == 202

    # 3. A reset link rotates `verified@`'s password and revokes every session it had.
    reset_token = seed_persona.FIXTURE_TOKENS["reset"][1].format(n=1)
    assert (await client.post("/api/auth/password/reset",
                              json={"token": reset_token, "password": RESET_FLOW_PW})).status_code == 200

    # 4. An invitation sets the first password `invited@` has ever had.
    invite_token = seed_persona.FIXTURE_TOKENS["invite"][1].format(n=1)
    assert (await client.post("/api/auth/accept-invite",
                              json={"token": invite_token, "password": INVITE_FLOW_PW})).status_code == 200

    # 5. The applicant under review answers and re-submits: the row goes `pending`, carries the
    #    answer, and the account moves with it.
    _nid, cookies, hdr = _session(conn, redis, seed_persona.NEEDS_REVIEW_EMAIL)
    mine = (await client.get("/api/applications/me", headers=auth_headers(cookies))).json()
    assert (await client.post(f"/api/applications/{mine['current']['id']}/answer",
                              headers=auth_headers(cookies, hdr), json={"answer": ANSWER})).status_code == 200

    # 6. The declined applicant re-applies: a SECOND application row, and the account is open again.
    _did, cookies, hdr = _session(conn, redis, seed_persona.DECLINED_EMAIL)
    reapply = await client.post("/api/applications", headers=auth_headers(cookies, hdr),
                                json={"kind": "buyer", "fields": seed_persona.DECLINED_FIELDS})
    assert reapply.status_code == 202, reapply.text


async def test_the_seed_restores_every_fixture_a_live_run_mutates(client, conn, redis, monkeypatch):  # noqa: F811
    """The whole of S7 in one assertion: seed → snapshot → mutate exactly as a live run does →
    seed again → the snapshot is what it was.

    This is what makes a QA run repeatable "without manual intervention" (John, 2026-09-08). Until
    it passes, the second of two live QA runs photographs a `verify-me@` that is already `verified`,
    a `verified@` whose password the harness no longer holds, an `invited@` with a password, an
    answered application where `gate-answer` expects a question, and a `declined@` with two rows.
    """
    monkeypatch.setenv("PERSONA_PASSWORD", PERSONA_PW)
    assert len(_fixture_emails()) == 10, "ten fixture accounts (A-S5.2); a new one joins the snapshot deliberately"

    _run_seed()
    baseline = _snapshot(conn)

    # The baseline IS the documented starting state, spelled out — so a failure below names what
    # moved rather than dumping two dictionaries.
    assert {email: acc["state"] for email, acc in baseline["accounts"].items()} == {
        "design@practice-match.test": "active",
        "buyer@practice-match.test": "active",
        "seller@practice-match.test": "active",
        "pending@practice-match.test": "pending",
        "needs-review@practice-match.test": "needs_review",
        "declined@practice-match.test": "declined",
        "unverified@practice-match.test": "unverified",
        "verify-me@practice-match.test": "unverified",
        "verified@practice-match.test": "verified",
        "invited@practice-match.test": "verified",
    }
    assert baseline["accounts"][seed_persona.INVITED_EMAIL]["password_opens"] == (), \
        "the invite token is the only way into `invited@`"
    for email, account in baseline["accounts"].items():
        if email != seed_persona.INVITED_EMAIL:
            assert account["password_opens"] == ("persona",), email
    for purpose, (owner, _pattern) in seed_persona.FIXTURE_TOKENS.items():
        assert baseline["tokens"][owner].count((purpose, f"{purpose}-01", False)) == 1, purpose
        assert sum(1 for p, _label, used in baseline["tokens"][owner] if p == purpose and not used) == 12, purpose
    assert baseline["outbox"] == [] and baseline["suppressions"] == [], "the seed enqueues nothing"
    assert baseline["throwaways"] == [], "and a fresh seed leaves no throwaway sign-up behind"

    await _mutate_as_a_live_run_does(client, conn, redis)
    mutated = _snapshot(conn)
    assert mutated != baseline, "the mutation must actually have happened, or the test below proves nothing"

    _run_seed()
    restored = _snapshot(conn)

    # Named first, so a regression says WHICH fixture the seed stopped owning.
    assert restored["accounts"] == baseline["accounts"], "accounts: state, roles, and which password opens them"
    assert restored["applications"] == baseline["applications"], "applications: no stray row, every field back"
    assert restored["tokens"] == baseline["tokens"], "tokens: consumed ones replaced, and no extra one left behind"
    assert restored["outbox"] == [] and restored["suppressions"] == [], "mail: the fixtures' queued rows are gone"
    assert restored["throwaways"] == [], "the run's throwaway sign-up account is gone"
    assert restored == baseline


async def test_the_seed_removes_the_fixtures_mail_rows_and_nobody_else_s(client, conn, redis, monkeypatch):  # noqa: F811
    """Fix round 1, ruling 2 (2026-09-08), which OVERTURNS S7's first decision to leave these rows.

    They are addressed to `@practice-match.test` — RFC 6761, never deliverable — so they are test
    artefacts, not product output, and on QA a real worker retries them for ever and can end up
    writing `email_suppression` rows against the fixture addresses. The delete is by EXACT address,
    never by pattern: a row for anyone else must be untouched, whatever it looks like.
    """
    monkeypatch.setenv("PERSONA_PASSWORD", PERSONA_PW)
    _run_seed()

    with conn.cursor() as cur:
        cur.execute("""INSERT INTO email_outbox (to_email, template, idempotency_key) VALUES
                       (%s,'verify_email','fix1-fixture'), (%s,'verify_email','fix1-stranger')""",
                    ("unverified@practice-match.test", "someone@example.org"))
        cur.execute("""INSERT INTO email_suppression (email, reason) VALUES (%s,'bounce'), (%s,'bounce')""",
                    ("unverified@practice-match.test", "someone@example.org"))
    await _mutate_as_a_live_run_does(client, conn, redis)
    assert _outbox_count(conn) > 1, "the flows really do queue mail to the fixture addresses"

    _run_seed()

    with conn.cursor() as cur:
        cur.execute("SELECT to_email FROM email_outbox ORDER BY to_email")
        remaining = [row[0] for row in cur.fetchall()]
        assert "unverified@practice-match.test" not in remaining, "the fixture's queued mail must be gone"
        assert remaining.count("someone@example.org") == 1, "and the stranger's row must survive untouched"
        assert not [e for e in remaining if e.endswith("@practice-match.test")], "no fixture address is left queued"
        cur.execute("SELECT email FROM email_suppression ORDER BY email")
        assert [row[0] for row in cur.fetchall()] == ["someone@example.org"]


def test_the_seed_removes_the_run_s_throwaway_sign_ups_and_not_a_lookalike(conn, monkeypatch):
    """Fix round 1, ruling 4 (2026-09-08). `POST /api/auth/signup` in the live flow creates a REAL
    account at `e2e-<run>-<purpose>-<n>@example.org` every run, and nothing owned it — on QA they
    accumulated one per run for ever.

    The pattern is anchored at both ends with a literal `@example.org`, so the trap here is a
    lookalike with the SAME local part at a domain the seed has no business touching: a SQL
    `LIKE 'e2e-%@example.org'` would delete it, and this test is what refuses that shortcut. The
    account's dependent rows go with it through the schema's own `ON DELETE CASCADE`.
    """
    monkeypatch.setenv("PERSONA_PASSWORD", PERSONA_PW)
    _run_seed()

    with conn.cursor() as cur:
        for email in (THROWAWAY_EMAIL, LOOKALIKE_EMAIL):
            cur.execute("""INSERT INTO account (email, password_hash, state) VALUES (%s,'!x','unverified')
                           RETURNING id""", (email,))
            account_id = cur.fetchone()[0]
            cur.execute("""INSERT INTO email_token (account_id, purpose, token_hash, expires_at)
                           VALUES (%s,'verify',%s, now() + interval '24 hours')""", (account_id, f"hash-of-{email}"))
        cur.execute("""INSERT INTO email_outbox (to_email, template, idempotency_key) VALUES
                       (%s,'verify_email','fix4-throwaway'), (%s,'verify_email','fix4-lookalike')""",
                    (THROWAWAY_EMAIL, LOOKALIKE_EMAIL))

    _run_seed()

    with conn.cursor() as cur:
        cur.execute("SELECT email FROM account WHERE email = ANY(%s) ORDER BY email",
                    ([THROWAWAY_EMAIL, LOOKALIKE_EMAIL],))
        assert [row[0] for row in cur.fetchall()] == [LOOKALIKE_EMAIL], \
            "the throwaway goes; the lookalike at another domain stays"
        cur.execute("SELECT count(*) FROM email_token WHERE token_hash = %s", (f"hash-of-{THROWAWAY_EMAIL}",))
        assert cur.fetchone()[0] == 0, "its dependent rows go with it (ON DELETE CASCADE)"
        cur.execute("SELECT count(*) FROM email_token WHERE token_hash = %s", (f"hash-of-{LOOKALIKE_EMAIL}",))
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT to_email FROM email_outbox WHERE to_email = ANY(%s)",
                    ([THROWAWAY_EMAIL, LOOKALIKE_EMAIL],))
        assert [row[0] for row in cur.fetchall()] == [LOOKALIKE_EMAIL], "and so does its queued mail"
