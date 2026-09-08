"""Quarterly licence audit (spec §9, §12). Fetches each registered dataset's terms URL, hashes
the body, and flags the dataset when the hash changes from the last time it was recorded. Never
changes `license_status` -- that stays a human decision recorded through the admin console (A9).

`license_audit_log` is the licence LEDGER, a distinct thing from the security audit trail
(`app.auth.audit`, A-C0 ¶3's `AUDITED`/`REAUTH` machinery) -- nothing here writes to `audit_log`
and nothing there writes to this table.

A dataset with no `license_url` (`aies`, `imagery`, `pet_ownership`, `practice_locations` --
migration `017_census_registry.sql`) has nothing to re-check and is skipped outright, never
recorded as a check that never happened. A transport failure or a non-2xx response is recorded
with no hash and `changed = false` -- an unresolved check is not evidence of drift, and drift is
flagged only once a REAL prior hash disagrees with a real new one."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import httpx
import psycopg2.extensions


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
        try:
            resp = http.get(url, timeout=httpx.Timeout(connect=15.0, read=45.0, write=15.0, pool=15.0), follow_redirects=True)
            status: int | None = resp.status_code
            digest: str | None = hashlib.sha256(resp.content).hexdigest() if resp.status_code < 400 else None
        except httpx.HTTPError:
            status, digest = None, None
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content_sha256 FROM license_audit_log WHERE dataset_key = %s AND content_sha256 IS NOT NULL ORDER BY checked_at DESC LIMIT 1",
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
