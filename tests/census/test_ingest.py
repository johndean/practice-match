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


def _notes(conn, run_id):
    with conn.cursor() as cur:
        cur.execute("SELECT notes FROM ingest_run WHERE id=%s", (run_id,))
        return cur.fetchone()[0]


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


# --- `Run.notes` reaches the ledger row (Task CENSUS-204, defect 3) ---------------------------
# The dataclass has carried a `notes` list since A5 and nothing ever read it, so a loader that
# skipped part of its work had nowhere to say so and the run still read `succeeded`. Defect 3
# requires the `ingest_run` row itself to name what was skipped and why, which is what this
# column is for -- `error_detail` is for the thing that ENDED a run, not for what it survived.

def test_notes_are_recorded_on_a_succeeded_run(conn):
    with ingest.run(conn, "acs5", VINTAGE) as run:
        run.notes.append("no data for state 02; skipped")
        run.notes.append("no data for state 26; skipped")
    assert _run_row(conn, run.id)[0] == "succeeded"
    assert _notes(conn, run.id) == "no data for state 02; skipped\nno data for state 26; skipped"


def test_a_run_with_no_notes_records_null_not_an_empty_string(conn):
    """NULL is "nothing was skipped"; an empty string would be a claim that something was
    recorded and read as blank."""
    with ingest.run(conn, "acs5", VINTAGE) as run:
        run.rows = 0
    assert _notes(conn, run.id) is None


def test_notes_survive_a_failure_so_what_was_skipped_before_it_is_still_readable(conn):
    with pytest.raises(RuntimeError), ingest.run(conn, "acs5", VINTAGE) as run:
        run.notes.append("no data for state 02; skipped")
        raise RuntimeError("boom")
    assert _run_row(conn, run.id)[0] == "failed"
    assert _notes(conn, run.id) == "no data for state 02; skipped"
