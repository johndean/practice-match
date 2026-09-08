"""Quarterly licence audit (spec §9, §12). Fetches each registered dataset's terms URL, hashes
the body, and flags the dataset when the hash changes from the last time it was recorded. Never
changes `license_status` -- that stays a human decision recorded through the admin console (A9).

`license_audit_log` is the licence LEDGER, a distinct thing from the security audit trail
(`app.auth.audit`, A-C0 ¶3's `AUDITED`/`REAUTH` machinery) -- nothing here writes to `audit_log`
and nothing there writes to this table.

A dataset with no `license_url` (`aies`, `imagery`, `pet_ownership`, `practice_locations` --
migration `017_census_registry.sql`) has nothing to re-check and is skipped outright, never
recorded as a check that never happened. A transport failure, a malformed URL, an over-bound
body or a non-2xx response is recorded with no hash and `changed = false` -- an unresolved check
is not evidence of drift, and drift is flagged only once a REAL prior hash disagrees with a real
new one.

A-C8 fix round (2026-09-09; m2, m3, m4 closed here):
  - **m2 — per-dataset isolation.** The `except` used to name only `httpx.HTTPError`, so a
    malformed `license_url` (`httpx.InvalidURL`, raised while building the request -- before any
    request is even attempted -- and NOT a subclass of `HTTPError`; A9's admin console makes
    `license_url` an editable field, which is how a bad value gets there) escaped the loop and
    aborted the whole quarterly sweep, leaving every dataset alphabetically after the bad row
    unchecked. The broad `except Exception` below is deliberate: one bad row becomes an
    unresolved check for THAT dataset only, and the sweep continues. Only the exception's TYPE
    NAME is logged, never its text, which could carry the malformed URL itself.
  - **m3 — the previous-hash lookup breaks a `checked_at` tie by `id`.** `checked_at DEFAULT
    now()` is the *transaction* timestamp, so two checks logged inside one non-autocommit
    connection (this module never commits itself -- a caller's concern) can share an identical
    timestamp, leaving `ORDER BY checked_at DESC LIMIT 1` to pick an arbitrary one of them.
    `, id DESC` makes the row inserted last -- unambiguous, since `id` is a `bigserial` -- the one
    actually compared against.
  - **m4 — the body is read under `CensusClient`'s own bound.** `resp.content` used to read the
    terms page unbounded, the exact hazard `MAX_RESPONSE_BYTES` (A3 review m2) exists for: a
    terms host serving an oversized or mis-routed body must not inflate a scheduled worker's
    memory. `_bounded_body` (`app/census/client.py`) is reused directly -- the SAME 64 MiB bound
    every other Census fetch already enforces, not a second implementation -- and going over it
    raises `ValueError`, caught by the same broad `except Exception` above.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

import httpx
import psycopg2.extensions

from app.census.client import _bounded_body

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditResult:
    dataset_key: str
    changed: bool
    sha256: str | None
    status: int | None


def audit(conn: psycopg2.extensions.connection, http: httpx.Client) -> list[AuditResult]:
    out: list[AuditResult] = []
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_key, license_url FROM dataset_registry WHERE license_url IS NOT NULL ORDER BY dataset_key")
        targets = cur.fetchall()
    for key, url in targets:
        status: int | None
        digest: str | None
        try:
            with http.stream(
                "GET", url, timeout=httpx.Timeout(connect=15.0, read=45.0, write=15.0, pool=15.0), follow_redirects=True
            ) as resp:
                digest = hashlib.sha256(_bounded_body(resp, url)).hexdigest() if resp.status_code < 400 else None
                status = resp.status_code
        except (httpx.HTTPError, httpx.InvalidURL, UnicodeError, ValueError) as exc:
            # m2: `httpx.InvalidURL` (a malformed license_url, raised while building the request)
            # and `UnicodeError` (an unencodable host) do NOT derive from `httpx.HTTPError`, so a
            # bare `except httpx.HTTPError` let either one escape the loop and abort the whole
            # sweep; `ValueError` is m4's over-bound body (`_bounded_body` above). Named, not
            # blind (ruff BLE001) -- these four are every hazard this fetch can raise. One bad row
            # becomes an unresolved check for THAT dataset only; the sweep continues past it. Only
            # the exception's TYPE is logged, never its text, which could carry the url.
            log.error("[census] license audit fetch failed for %s: %s", key, type(exc).__name__)
            status, digest = None, None
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content_sha256 FROM license_audit_log WHERE dataset_key = %s AND content_sha256 IS NOT NULL "
                "ORDER BY checked_at DESC, id DESC LIMIT 1",
                (key,),
            )
            prev = cur.fetchone()
            changed = bool(prev and digest and prev[0] != digest)
            cur.execute(
                "INSERT INTO license_audit_log (dataset_key, url, content_sha256, http_status, changed) VALUES (%s, %s, %s, %s, %s)",
                (key, url, digest, status, changed),
            )
            if changed:
                cur.execute("UPDATE dataset_registry SET drift_flagged = true WHERE dataset_key = %s", (key,))
            elif digest:
                cur.execute("UPDATE dataset_registry SET last_verified_at = now() WHERE dataset_key = %s", (key,))
        out.append(AuditResult(key, changed, digest, status))
    return out
