import pytest

from app.census import ingest, vintage


def _seed(conn, ds, vint, n, status="succeeded", offset=0):
    """`offset` keeps two datasets' geo_ids disjoint when they are seeded at the SAME vintage
    (A-C7 M2's own test): real `acs5`/`acs5_subject` rows never collide on the PK because they
    write different variables, but this helper always writes `B01003_001E`."""
    with ingest.run(conn, ds, vint) as run:
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO acs_measure VALUES (%s,'140',%s,'B01003_001E',1,0,%s)", [(f"g{offset + i}", vint, run.id) for i in range(n)])
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


def test_ratio_within_bounds_activates_without_force(conn):
    """m1 (A7 review Minor 1): the *pass* side of the ratio guard was never exercised -- only the
    refused (0.4) and no-prior (`ratio is None`) paths were. This pins the ordinary, expected
    case: a modest, in-band row-count change activates on its own, no `--force` needed."""
    _seed(conn, "acs5", "2019\u20132023", 100)
    vintage.activate(conn, "acs5", "2019\u20132023", by="john")
    _seed(conn, "acs5", "2020\u20132024", 90)   # 90% of prior -> ratio 0.9, comfortably in bounds
    rep = vintage.activate(conn, "acs5", "2020\u20132024", by="john")
    assert rep.ratio == 0.9
    assert vintage.active(conn)["acs5"] == "2020\u20132024"


def test_ratio_exactly_at_the_low_bound_activates(conn):
    """m1: `LOW <= ratio <= HIGH` is inclusive -- a mutant narrowing either bound, or flipping
    `<=` to `<`, must fail this exact-boundary case."""
    _seed(conn, "acs5", "2019\u20132023", 100)
    vintage.activate(conn, "acs5", "2019\u20132023", by="john")
    _seed(conn, "acs5", "2020\u20132024", 80)   # exactly ratio 0.8 -> the inclusive low bound
    rep = vintage.activate(conn, "acs5", "2020\u20132024", by="john")
    assert rep.ratio == 0.8
    assert vintage.active(conn)["acs5"] == "2020\u20132024"


def test_force_cannot_bypass_a_failed_run(conn):
    """I2 (A7 review): only the ratio clause carries `and not force` -- the succeeded-run check
    is unconditional, so `force=True` must never resurrect a failed or aborted run."""
    with pytest.raises(RuntimeError):
        _seed(conn, "acs5", "2020\u20132024", 5, status="failed")
    with pytest.raises(vintage.ActivationRefused):
        vintage.activate(conn, "acs5", "2020\u20132024", by="john", force=True)


def test_qa_reports_no_run_status_for_a_never_ingested_vintage(conn):
    """No `ingest_run` row at all (an operator typo, or a vintage nobody has loaded yet) is
    distinct from a `failed`/`aborted` run -- both refuse activation, but `qa()` on its own must
    say so plainly rather than raising."""
    rep = vintage.qa(conn, "acs5", "2030\u20132034")
    assert rep.rows_new == 0 and rep.last_run_status is None
    with pytest.raises(vintage.ActivationRefused):
        vintage.activate(conn, "acs5", "2030\u20132034", by="john")


def test_dataset_scoped_counts_do_not_blend_datasets_sharing_a_table_and_vintage(conn):
    """A-C7 M2 (task-A7-review Major 2): `acs5` and `acs5_subject` share `acs_measure`, and in
    real registry data carry the SAME vintage string across a release cycle -- a vintage-only
    count blends them. Seed both at an OLD vintage and activate `acs5_subject` there (its own
    prior); seed both again at a NEW vintage where `acs5_subject`'s own fetch legitimately
    returns zero rows but the run still succeeds. An unscoped diff would compute
    `ratio = acs5's 90 rows / (acs5's 90 + acs5_subject's 10) = 0.9` -- comfortably in bounds,
    letting an empty dataset go live. Scoped by `ingest_run.dataset_key`, `acs5_subject`'s own
    ratio is `0 / 10 = 0.0`, well outside `[0.8, 1.25]`, and the activation is refused."""
    _seed(conn, "acs5", "2018\u20132022", 90)
    _seed(conn, "acs5_subject", "2018\u20132022", 10, offset=1000)
    vintage.activate(conn, "acs5_subject", "2018\u20132022", by="john")
    _seed(conn, "acs5", "2019\u20132023", 90)
    _seed(conn, "acs5_subject", "2019\u20132023", 0, offset=1000)
    with pytest.raises(vintage.ActivationRefused):
        vintage.activate(conn, "acs5_subject", "2019\u20132023", by="john")
    assert vintage.active(conn)["acs5_subject"] == "2018\u20132022"


def test_reactivating_the_current_vintage_is_a_no_op_diff(conn):
    """Re-running `activate` on the vintage that is already active must not divide the vintage's
    own row count against itself -- `qa()` treats `prior == vint` the same as "no prior vintage
    yet" (`rows_prior=0`, `ratio=None`, `prior_vintage=None`), so this never spuriously refuses."""
    _seed(conn, "acs5", "2019\u20132023", 10)
    vintage.activate(conn, "acs5", "2019\u20132023", by="john")
    rep = vintage.activate(conn, "acs5", "2019\u20132023", by="john")
    assert rep.prior_vintage is None and rep.rows_prior == 0 and rep.ratio is None
    assert vintage.active(conn)["acs5"] == "2019\u20132023"


def test_activate_stores_and_returns_a_note(conn):
    """A-C7 concern 1: the ledger's 'why' used to live only in a CLI's stdout at the moment it
    ran. `active_vintage.note` persists it; the returned `Report` carries the SAME note back so
    the CLI can print it too."""
    _seed(conn, "acs5", "2019\u20132023", 10)
    rep = vintage.activate(conn, "acs5", "2019\u20132023", by="john", note="initial launch")
    assert rep.note == "initial launch"
    with conn.cursor() as cur:
        cur.execute("SELECT note FROM active_vintage WHERE dataset_key = 'acs5'")
        assert cur.fetchone() == ("initial launch",)


def test_activate_note_defaults_to_none_and_can_be_updated_by_a_later_activation(conn):
    _seed(conn, "acs5", "2019\u20132023", 10)
    rep = vintage.activate(conn, "acs5", "2019\u20132023", by="john")
    assert rep.note is None
    with conn.cursor() as cur:
        cur.execute("SELECT note FROM active_vintage WHERE dataset_key = 'acs5'")
        assert cur.fetchone() == (None,)
    rep2 = vintage.activate(conn, "acs5", "2019\u20132023", by="john", note="re-confirmed")
    assert rep2.note == "re-confirmed"
    with conn.cursor() as cur:
        cur.execute("SELECT note FROM active_vintage WHERE dataset_key = 'acs5'")
        assert cur.fetchone() == ("re-confirmed",)
