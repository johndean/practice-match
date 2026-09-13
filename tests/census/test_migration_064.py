"""migrations/064_geo_metric.sql — `market_metric`'s sibling, per geography (D-NS1, D-NS3).

Modelled on tests/census/test_migration_062.py, which proves the twin trigger on `market_metric`.
The trigger's UPDATE arm is asserted as well as its INSERT arm: `061`'s equivalent fired
`BEFORE INSERT OR UPDATE` for months and was only ever exercised by INSERTs (finding 1, A-C16)."""
import psycopg2
import pytest


def _row(conn: psycopg2.extensions.connection, dataset: str = "acs5", geo_id: str = "78704") -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO geo_metric (geo_id, summary_level, vintage, metric_key, value_num, unit, source_dataset, computed_at) "
            "VALUES (%s, '860', '2019\u20132023', 'median_hh_income', 92150, 'usd', %s, now())",
            (geo_id, dataset),
        )


def test_the_table_carries_market_metrics_own_column_vocabulary(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'geo_metric' ORDER BY column_name")
        cols = {name: (dtype, nullable) for name, dtype, nullable in cur.fetchall()}
    assert sorted(cols) == [
        "computed_at", "formula_version", "geo_id", "inputs", "is_derived", "metric_key",
        "moe", "source_dataset", "summary_level", "suppress_reason", "suppressed", "unit",
        "value_num", "vintage",
    ]
    assert cols["summary_level"][0] == "character"
    assert cols["value_num"] == ("numeric", "YES"), "a geography with no figure must be storable"
    assert cols["moe"] == ("numeric", "YES")
    assert cols["inputs"][0] == "jsonb"
    for required in ("geo_id", "summary_level", "vintage", "metric_key", "unit", "is_derived", "suppressed", "source_dataset", "computed_at"):
        assert cols[required][1] == "NO", required


def test_the_primary_key_is_geography_metric_vintage_and_the_read_paths_index_exists(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'geo_metric' ORDER BY indexname"
        )
        idx = dict(cur.fetchall())
    assert "geo_metric_pkey" in idx
    for column in ("geo_id", "summary_level", "vintage", "metric_key"):
        assert column in idx["geo_metric_pkey"], column
    # The read path's ONLY access pattern: one layer, one geography level, one vintage.
    assert "geo_metric_layer_idx" in idx
    assert "summary_level" in idx["geo_metric_layer_idx"] and "metric_key" in idx["geo_metric_layer_idx"] and "vintage" in idx["geo_metric_layer_idx"]


def test_a_second_row_for_the_same_geography_metric_and_vintage_conflicts(conn: psycopg2.extensions.connection) -> None:
    _row(conn)
    with pytest.raises(psycopg2.errors.UniqueViolation):
        _row(conn)


def test_the_licence_gate_admits_a_cleared_dataset(conn: psycopg2.extensions.connection) -> None:
    _row(conn, "acs5")
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM geo_metric")
        assert cur.fetchone()[0] == 1


@pytest.mark.parametrize("status", ["unresolved", "blocked"])
def test_the_licence_gate_refuses_a_dataset_that_is_not_cleared(conn: psycopg2.extensions.connection, status: str) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = %s WHERE dataset_key = 'acs5'", (status,))
    with pytest.raises(psycopg2.errors.RaiseException) as exc:
        _row(conn, "acs5")
    assert "geo_metric write refused" in str(exc.value)
    # `062`'s own correction: the message names the dataset KEY, which cannot go stale, and never
    # the status it happened to read a second time.
    assert status not in str(exc.value)
    assert "acs5" in str(exc.value)


def test_the_licence_gate_refuses_a_dataset_with_no_registry_row_at_all(conn: psycopg2.extensions.connection) -> None:
    """`IS DISTINCT FROM` catches NULL: a key the registry does not carry is not a key awaiting a
    decision.

    MEASURED, because the plan's draft asserted the opposite and would have made this test
    vacuous: the refusal is the TRIGGER's (`psycopg2.errors.RaiseException`, SQLSTATE P0001),
    not the foreign key's. The trigger is `BEFORE INSERT`, and a foreign key is enforced by an
    AFTER-row constraint trigger, so the gate always speaks first. Asserted strictly on that
    class and on the message for exactly that reason: `raises((RaiseException,
    ForeignKeyViolation))` would still pass with the trigger dropped, because the foreign key
    would refuse instead — which proves nothing about the gate."""
    with pytest.raises(psycopg2.errors.RaiseException) as exc:
        _row(conn, "not_a_dataset")
    assert "geo_metric write refused" in str(exc.value)
    assert "not_a_dataset" in str(exc.value)


def test_the_licence_gate_fires_on_UPDATE_as_well_as_INSERT(conn: psycopg2.extensions.connection) -> None:
    """`061`'s equivalent fired BEFORE INSERT OR UPDATE and was only ever exercised by INSERTs
    (A-C16 finding 1). Existing rows survive a status flip — the read path hides them within 60 s
    — but a WRITE naming an uncleared dataset is refused whichever statement makes it."""
    _row(conn, "acs5")
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'blocked' WHERE dataset_key = 'acs5'")
        cur.execute("SELECT count(*) FROM geo_metric")
        assert cur.fetchone()[0] == 1, "an existing row must survive the flip"
    with conn.cursor() as cur, pytest.raises(psycopg2.errors.RaiseException):
        cur.execute("UPDATE geo_metric SET value_num = 1 WHERE geo_id = '78704'")


def test_the_migration_manages_no_transaction_of_its_own(conn: psycopg2.extensions.connection) -> None:
    """`tests/test_migrate.py::test_migration_files_never_manage_their_own_transaction` reads a `;`
    immediately before `BEGIN` as a self-managed transaction, which is why `061` and `062` open
    their trigger bodies straight on `$$\\nBEGIN` with no DECLARE section. Asserted here too, at
    the file the runner will actually apply.

    The check is made on the SQL with `--` line comments stripped, exactly as `test_migrate.py`'s
    own regex does. A bare `"DECLARE" not in sql` — the plan's draft — matches the word in the
    prose that EXPLAINS why there is no DECLARE section, so it fails on `061` (2 occurrences) and
    `062` (2) as readily as on this file, and tests prose rather than code."""
    from pathlib import Path

    sql = (Path(__file__).resolve().parents[2] / "migrations" / "064_geo_metric.sql").read_text(encoding="utf-8")
    code = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    assert "DECLARE" not in code.upper()
    assert "$$\nBEGIN" in code
