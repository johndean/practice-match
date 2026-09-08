import pytest

from app.census import ingest, vintage


def _seed(conn, ds, vint, n, status="succeeded"):
    with ingest.run(conn, ds, vint) as run:
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO acs_measure VALUES (%s,'140',%s,'B01003_001E',1,0,%s)", [(f"g{i}", vint, run.id) for i in range(n)])
        run.rows = n
        if status == "failed":
            raise RuntimeError("seeded failure")


def test_activation_requires_a_succeeded_run(conn):
    with pytest.raises(RuntimeError):
        _seed(conn, "acs5", "2019\u20132023", 5, status="failed")
    with pytest.raises(vintage.ActivationRefused):
        vintage.activate(conn, "acs5", "2019\u20132023", by="john")


def test_first_vintage_activates_and_is_readable(conn):
    _seed(conn, "acs5", "2019\u20132023", 10)
    rep = vintage.activate(conn, "acs5", "2019\u20132023", by="john")
    assert rep.rows_new == 10 and rep.prior_vintage is None
    assert vintage.active(conn)["acs5"] == "2019\u20132023"


def test_large_row_swing_is_refused_unless_forced(conn):
    _seed(conn, "acs5", "2019\u20132023", 100)
    vintage.activate(conn, "acs5", "2019\u20132023", by="john")
    _seed(conn, "acs5", "2020\u20132024", 40)   # 60% drop → refused
    with pytest.raises(vintage.ActivationRefused):
        vintage.activate(conn, "acs5", "2020\u20132024", by="john")
    assert vintage.active(conn)["acs5"] == "2019\u20132023"
    rep = vintage.activate(conn, "acs5", "2020\u20132024", by="john", force=True)
    assert rep.ratio == 0.4 and vintage.active(conn)["acs5"] == "2020\u20132024"


def test_qa_reports_no_run_status_for_a_never_ingested_vintage(conn):
    """No `ingest_run` row at all (an operator typo, or a vintage nobody has loaded yet) is
    distinct from a `failed`/`aborted` run -- both refuse activation, but `qa()` on its own must
    say so plainly rather than raising."""
    rep = vintage.qa(conn, "acs5", "2030\u20132034")
    assert rep.rows_new == 0 and rep.last_run_status is None
    with pytest.raises(vintage.ActivationRefused):
        vintage.activate(conn, "acs5", "2030\u20132034", by="john")


def test_reactivating_the_current_vintage_is_a_no_op_diff(conn):
    """Re-running `activate` on the vintage that is already active must not divide the vintage's
    own row count against itself -- `qa()` treats `prior == vint` the same as "no prior vintage
    yet" (`rows_prior=0`, `ratio=None`, `prior_vintage=None`), so this never spuriously refuses."""
    _seed(conn, "acs5", "2019\u20132023", 10)
    vintage.activate(conn, "acs5", "2019\u20132023", by="john")
    rep = vintage.activate(conn, "acs5", "2019\u20132023", by="john")
    assert rep.prior_vintage is None and rep.rows_prior == 0 and rep.ratio is None
    assert vintage.active(conn)["acs5"] == "2019\u20132023"
