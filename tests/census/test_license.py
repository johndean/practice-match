"""Task A8: the quarterly licence audit (spec §9, §12). `license.audit()` re-reads each
registered dataset's terms URL, hashes the body, and flags `dataset_registry.drift_flagged`
when the hash changes from the last time it was recorded -- staff review the drift, nothing here
ever changes `license_status` itself. `license_audit_log` is the licence LEDGER (distinct from
the security audit trail, `app.auth.audit`, which A-C0 ¶3 governs separately)."""
import hashlib

import httpx

from app.census import license
from app.census.client import MAX_RESPONSE_BYTES


def test_audit_records_hash_then_flags_drift(conn):
    body = {"n": 0}

    def handler(r):
        return httpx.Response(200, text=f"terms v{body['n']}")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    first = {r.dataset_key: r for r in license.audit(conn, http)}
    assert first["acs5"].changed is False                     # first observation is the baseline
    second = {r.dataset_key: r for r in license.audit(conn, http)}
    assert second["acs5"].changed is False
    body["n"] = 1
    third = {r.dataset_key: r for r in license.audit(conn, http)}
    assert third["acs5"].changed is True
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM license_audit_log WHERE dataset_key='acs5' AND changed")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT drift_flagged FROM dataset_registry WHERE dataset_key='acs5'")
        assert cur.fetchone()[0] is True
        cur.execute("SELECT last_verified_at IS NOT NULL FROM dataset_registry WHERE dataset_key='acs5'")
        assert cur.fetchone()[0] is True


def test_datasets_without_a_terms_url_are_skipped(conn):
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="x")))
    keys = {r.dataset_key for r in license.audit(conn, http)}
    assert "imagery" not in keys and "pet_ownership" not in keys


def test_a_failed_fetch_is_recorded_with_no_hash_and_never_flags_drift(conn):
    """Every registered `license_url` is a real host over a real network in production; a
    transport failure (`httpx.HTTPError`, e.g. `httpx.ConnectError`) must not raise out of a
    quarterly beat task -- it is recorded as an unresolved check (`content_sha256 IS NULL`,
    `http_status IS NULL`) and left `changed = false`, never flagged as drift on no evidence."""
    def handler(r):
        raise httpx.ConnectError("boom", request=r)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    results = {r.dataset_key: r for r in license.audit(conn, http)}
    assert results["acs5"].sha256 is None
    assert results["acs5"].status is None
    assert results["acs5"].changed is False
    with conn.cursor() as cur:
        cur.execute("SELECT content_sha256, http_status, changed FROM license_audit_log WHERE dataset_key='acs5'")
        assert cur.fetchone() == (None, None, False)
        cur.execute("SELECT drift_flagged FROM dataset_registry WHERE dataset_key='acs5'")
        assert cur.fetchone()[0] is False


def test_a_non_2xx_response_is_recorded_with_the_status_but_no_hash(conn):
    """A dataset's terms page returning e.g. 404/500 is not "unchanged" and not "drift" -- it is
    an unresolved check with the status recorded for a human to see, the same no-hash/no-flag
    shape as a transport failure."""
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404, text="gone")))
    results = {r.dataset_key: r for r in license.audit(conn, http)}
    assert results["acs5"].sha256 is None
    assert results["acs5"].status == 404
    assert results["acs5"].changed is False


def test_a_malformed_license_url_is_isolated_and_the_sweep_continues(conn):
    """A-C8 (3) / m2: `license.audit` used to catch only `httpx.HTTPError`, so one bad row (e.g.
    an admin-edited `license_url` once A9 makes it editable) aborted the whole quarterly sweep --
    every dataset alphabetically after it went unchecked. `httpx.InvalidURL` is raised while
    building the request, before any request is even attempted, and does NOT derive from
    `httpx.HTTPError` -- exactly the escape the review found. `bds` sorts alphabetically before
    `cbp`/`qwi`/`tiger_cb` among the registry's non-null `license_url` rows, so corrupting it and
    still seeing the later datasets checked proves the sweep survives past the bad row."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_url = 'http://[::1' WHERE dataset_key = 'bds'")

    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="terms")))
    results = {r.dataset_key: r for r in license.audit(conn, http)}

    assert results["bds"].sha256 is None and results["bds"].status is None and results["bds"].changed is False
    assert results["cbp"].sha256 is not None   # the sweep reached every dataset AFTER the bad row
    assert results["qwi"].sha256 is not None
    assert results["tiger_cb"].sha256 is not None
    with conn.cursor() as cur:
        cur.execute("SELECT content_sha256, http_status, changed FROM license_audit_log WHERE dataset_key = 'bds'")
        assert cur.fetchone() == (None, None, False)


def test_previous_hash_lookup_breaks_a_checked_at_tie_by_id(conn):
    """A-C8 (4) / m3: `checked_at DEFAULT now()` is the TRANSACTION timestamp, so two checks
    logged inside one non-autocommit transaction (this module never commits -- a caller's
    concern) can carry an identical timestamp; `ORDER BY checked_at DESC LIMIT 1` alone then picks
    an arbitrary one of them as "previous". Seeded here as two rows sharing one `checked_at`: the
    higher-`id` row (inserted second) carries the hash that matches the next real check's body --
    `, id DESC` is what makes THAT row the one compared against, deterministically."""
    body = b"the terms body the tie-break test re-checks"
    matching_hash = hashlib.sha256(body).hexdigest()
    with conn.cursor() as cur:
        cur.execute("SELECT now()")
        (shared_ts,) = cur.fetchone()
        cur.execute(
            "INSERT INTO license_audit_log (dataset_key, url, content_sha256, http_status, changed, checked_at) VALUES (%s,%s,%s,%s,%s,%s)",
            ("acs5", "https://x", "deliberately-different-older-hash", 200, False, shared_ts),
        )
        cur.execute(
            "INSERT INTO license_audit_log (dataset_key, url, content_sha256, http_status, changed, checked_at) VALUES (%s,%s,%s,%s,%s,%s)",
            ("acs5", "https://x", matching_hash, 200, False, shared_ts),
        )
        cur.execute("SELECT count(*) FROM license_audit_log WHERE dataset_key = 'acs5' AND checked_at = %s", (shared_ts,))
        assert cur.fetchone()[0] == 2  # the tie is real: two rows, one shared timestamp

    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=body)))
    results = {r.dataset_key: r for r in license.audit(conn, http)}

    assert results["acs5"].sha256 == matching_hash
    assert results["acs5"].changed is False  # matched the higher-id row's hash, not the older one's


def test_a_terms_body_over_the_bound_is_recorded_as_that_datasets_error(conn):
    """A-C8 (5) / m4: the exact hazard `CensusClient.MAX_RESPONSE_BYTES` exists for (A3 review
    m2) -- a terms host serving an oversized or mis-routed body must not inflate a scheduled
    worker's memory. Reuses `CensusClient`'s own bound (`app.census.client._bounded_body`), whose
    declared-`Content-Length` branch is proven at 100 % branch already in
    `tests/census/test_client.py`; this test proves the INTEGRATION -- going over the bound here
    ends up "that dataset's error", the same no-hash/no-status shape as a transport failure."""
    def handler(r):
        return httpx.Response(200, text="tiny body", headers={"content-length": str(MAX_RESPONSE_BYTES + 1)})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    results = {r.dataset_key: r for r in license.audit(conn, http)}

    assert results["acs5"].sha256 is None
    assert results["acs5"].status is None
    assert results["acs5"].changed is False
