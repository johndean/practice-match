import pytest

from app.census import ingest, vintage


def _seed(conn, ds, vint, n, status="succeeded", offset=0, notes=()):
    """`offset` keeps two datasets' geo_ids disjoint when they are seeded at the SAME vintage
    (A-C7 M2's own test): real `acs5`/`acs5_subject` rows never collide on the PK because they
    write different variables, but this helper always writes `B01003_001E`.

    `notes` is what a loader's own skip arm appends when the Census answered "no data" for one
    geography and the run carried on without it (Task CENSUS-204, defect 3) -- the only thing
    that ever writes `ingest_run.notes`, and therefore the signal `activate()` reads."""
    with ingest.run(conn, ds, vint) as run:
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO acs_measure VALUES (%s,'140',%s,'B01003_001E',1,0,%s)", [(f"g{offset + i}", vint, run.id) for i in range(n)])
        run.rows = n
        run.notes.extend(notes)
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


# --- a partial vintage must never go active (Task CENSUS-204 fix round 1, Important-1) --------
# `app/census/ingest.py`'s own docstring has always stated the principle: `VariableMissing` is
# recorded `'aborted'` because it is "a schema drift (a partial vintage that must never go
# active)". The 204 tolerance crossed it by accident. BEFORE it, a 204 on one geography raised
# `JSONDecodeError`, `ingest.run` recorded `failed`, and the succeeded-run check below refused
# the vintage. AFTER it, the same run is `succeeded` with a note -- correct for the RUN, which
# genuinely completed with what the Census published, and wrong for ACTIVATION.
#
# The ratio guard cannot stand in for this and the two tests below measure why: on a first-ever
# activation `rows_prior == 0`, so `ratio is None` and the guard does not run at all; on a
# re-activation that loses one small summary level the ratio sits near 0.98, comfortably inside
# [0.8, 1.25]. `ingest_run.notes` is written by exactly one thing -- a loader's own `if rows is
# None:` skip arm, five of them, measured -- so "this run has notes" IS "this vintage is
# incomplete", which is precisely the decision `activate()` has to make.

SKIPPED_PLACE = "acs5: no data for summary level 160 (place:*, in state:48); skipped"


def test_a_vintage_whose_run_skipped_a_geography_is_refused_on_its_first_ever_activation(conn):
    """The hole the ratio guard cannot reach: no prior vintage, so `ratio is None` and the
    row-count check never runs. Nothing else looks at what the run skipped, so before this the
    partial vintage went live with no check whatsoever."""
    _seed(conn, "acs5", "2019\u20132023", 10, notes=[SKIPPED_PLACE])
    rep = vintage.qa(conn, "acs5", "2019\u20132023")
    assert rep.ratio is None                       # the ratio guard is not even applicable here
    with pytest.raises(vintage.ActivationRefused) as exc:
        vintage.activate(conn, "acs5", "2019\u20132023", by="john")
    assert "partial" in str(exc.value).lower()             # WHAT is wrong with the vintage
    assert "summary level 160" in str(exc.value)           # and WHICH geography it is missing
    assert "acs5" not in vintage.active(conn)


def test_a_small_loss_is_refused_where_the_ratio_would_have_waved_it_through(conn):
    """ACS loads six summary levels of very unequal size, so losing `state` (51 rows) or
    `county` (~3k of ~150k) leaves a ratio near 1.0. Measured here at exactly 0.98: inside the
    band, so the ratio guard PASSES, and the vintage is still partial."""
    _seed(conn, "acs5", "2019\u20132023", 100)
    vintage.activate(conn, "acs5", "2019\u20132023", by="john")
    _seed(conn, "acs5", "2020\u20132024", 98, offset=1000, notes=["acs5: no data for summary level 040 (state:*); skipped"])
    rep = vintage.qa(conn, "acs5", "2020\u20132024")
    assert rep.ratio == 0.98 and vintage.LOW <= rep.ratio <= vintage.HIGH
    with pytest.raises(vintage.ActivationRefused):
        vintage.activate(conn, "acs5", "2020\u20132024", by="john")
    assert vintage.active(conn)["acs5"] == "2019\u20132023"


def test_force_cannot_activate_a_partial_vintage(conn):
    """The route to activating a deliberately partial vintage is to RE-RUN the missing
    geographies, never to override the gate -- so the partial check carries no `force` term, in
    the same way the succeeded-run check above does not (I2, A7 review)."""
    _seed(conn, "acs5", "2019\u20132023", 10, notes=[SKIPPED_PLACE])
    with pytest.raises(vintage.ActivationRefused):
        vintage.activate(conn, "acs5", "2019\u20132023", by="john", force=True, note="I know")
    assert "acs5" not in vintage.active(conn)


def test_a_partial_refusal_reads_differently_from_a_ratio_refusal(conn):
    """An operator must be able to tell the two apart from the message alone, without reading
    the source: one says the vintage is incomplete and names what is missing, the other says the
    row count moved too far and names the bounds."""
    _seed(conn, "acs5", "2019\u20132023", 100)
    vintage.activate(conn, "acs5", "2019\u20132023", by="john")
    _seed(conn, "acs5", "2020\u20132024", 40, offset=1000)                      # ratio 0.4, no notes
    _seed(conn, "acs5", "2021\u20132025", 98, offset=2000, notes=[SKIPPED_PLACE])  # ratio 0.98, partial
    with pytest.raises(vintage.ActivationRefused) as ratio_exc:
        vintage.activate(conn, "acs5", "2020\u20132024", by="john")
    with pytest.raises(vintage.ActivationRefused) as partial_exc:
        vintage.activate(conn, "acs5", "2021\u20132025", by="john")
    assert "row count ratio" in str(ratio_exc.value) and "partial" not in str(ratio_exc.value).lower()
    assert "partial" in str(partial_exc.value).lower() and "row count ratio" not in str(partial_exc.value)


def test_re_running_the_missing_geographies_is_what_clears_the_gate(conn):
    """`qa()` reads the LATEST `ingest_run` for the vintage -- exactly as the succeeded-run
    check has always done -- so the documented route out (re-run what was skipped) works, and
    nothing needs an override flag."""
    _seed(conn, "acs5", "2019\u20132023", 10, notes=[SKIPPED_PLACE])
    with pytest.raises(vintage.ActivationRefused):
        vintage.activate(conn, "acs5", "2019\u20132023", by="john")
    _seed(conn, "acs5", "2019\u20132023", 0)   # the re-run upserts over the same rows and skips nothing
    rep = vintage.activate(conn, "acs5", "2019\u20132023", by="john")
    assert rep.run_notes is None and vintage.active(conn)["acs5"] == "2019\u20132023"


def test_qa_carries_the_run_notes_that_activate_then_decides_on(conn):
    """`Report` had no field for this at all, so nothing at the decision point could see it --
    the review's own sentence, "nothing reads `notes` at the decision point". `qa()` reads it
    from the same row it reads `last_run_status` from, in the same query."""
    _seed(conn, "acs5", "2019\u20132023", 10, notes=[SKIPPED_PLACE, "acs5: no data for summary level 860 (zip code tabulation area:*); skipped"])
    rep = vintage.qa(conn, "acs5", "2019\u20132023")
    assert rep.run_notes == SKIPPED_PLACE + "\nacs5: no data for summary level 860 (zip code tabulation area:*); skipped"
    assert rep.last_run_status == "succeeded"


def test_a_complete_run_carries_no_notes_and_activates_exactly_as_before(conn):
    """The gate must be invisible to every run that skipped nothing: `notes` is NULL, not an
    empty string, so this is a `None` check and never a truthiness test on a string."""
    _seed(conn, "acs5", "2019\u20132023", 10)
    rep = vintage.activate(conn, "acs5", "2019\u20132023", by="john")
    assert rep.run_notes is None and vintage.active(conn)["acs5"] == "2019\u20132023"
