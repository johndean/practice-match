"""Task A8: the quarterly licence audit (spec §9, §12). `license.audit()` re-reads each
registered dataset's terms URL, hashes the body, and flags `dataset_registry.drift_flagged`
when the hash changes from the last time it was recorded -- staff review the drift, nothing here
ever changes `license_status` itself. `license_audit_log` is the licence LEDGER (distinct from
the security audit trail, `app.auth.audit`, which A-C0 ¶3 governs separately)."""
import httpx

from app.census import license


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
