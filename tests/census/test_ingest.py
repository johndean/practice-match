"""`ingest_run` lifecycle (spec §13; task A5 brief). Data written inside `ingest.run()` is one
transaction: committed on success, rolled back on any failure -- the run row always records the
outcome, whichever way it goes. `VariableMissing` is recorded as `aborted` (schema drift, a
partial vintage that must never go active) rather than `failed` (an ordinary outage)."""
import pytest

from app.census import ingest
from app.census.client import VariableMissing

VINTAGE = "2019\u20132023"  # en dash, as the registry seeds it (migrations/017_census_registry.sql)


def _run_row(conn, run_id):
    with conn.cursor() as cur:
        cur.execute("SELECT status, rows_written, request_count, error_detail, finished_at IS NOT NULL FROM ingest_run WHERE id=%s", (run_id,))
        return cur.fetchone()


def test_success_commits_and_records_counts(conn):
    with ingest.run(conn, "acs5", VINTAGE) as run:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO acs_measure VALUES ('1','010',%s,'B01003_001E', 331000000, 0, %s)", (VINTAGE, run.id))
        run.rows += 1
        run.requests = 1
    assert _run_row(conn, run.id) == ("succeeded", 1, 1, None, True)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM acs_measure")
        assert cur.fetchone()[0] == 1


def test_failure_rolls_back_data_and_records_error(conn):
    with pytest.raises(RuntimeError), ingest.run(conn, "acs5", VINTAGE) as run:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO acs_measure VALUES ('1','010',%s,'B01003_001E', 1, 0, %s)", (VINTAGE, run.id))
        raise RuntimeError("boom")
    status, _rows, _requests, err, _finished = _run_row(conn, run.id)
    assert status == "failed" and "boom" in err
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM acs_measure")
        assert cur.fetchone()[0] == 0


def test_variable_drift_is_recorded_as_aborted(conn):
    with pytest.raises(VariableMissing), ingest.run(conn, "acs5", VINTAGE):
        raise VariableMissing(["B19013_001E"])
    with conn.cursor() as cur:
        cur.execute("SELECT status, error_detail FROM ingest_run ORDER BY id DESC LIMIT 1")
        status, err = cur.fetchone()
    assert status == "aborted" and "B19013_001E" in err
