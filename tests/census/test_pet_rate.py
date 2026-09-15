"""The pet-household incidence rate, its provenance, and the rule that there is only one of it.

Task PET-RATE-PROVENANCE (John's requirement of 2026-09-15). The rate was `0.57` — a bare literal
in `app/census/metrics.py` whose only explanation was the word "placeholder" in its own comment —
and the frontend kept a second, independent copy of it. This module is the ONE place the active
rate is written down, with enough beside it to reconstruct how any figure derived from it was
produced.
"""
from __future__ import annotations

import app.census.metrics as M
from app.census import pet_rate as PR


def test_the_active_rate_is_the_2025_avma_figure() -> None:
    """John's ruling: 0.586, the AVMA 2025 Sourcebook's share of U.S. households owning at least
    one pet. The display string is the source's own rounding, not a format of the float."""
    assert PR.INCIDENCE_RATE == 0.586
    assert PR.INCIDENCE_RATE_DISPLAY == "58.6%"


def test_there_is_exactly_one_rate_and_metrics_re_exports_it() -> None:
    """`M.PET_RATE` is the name four call sites already read. It is a BINDING to the one
    definition, never a second literal — which is what "no component holds an independent
    hard-coded production rate" means at the level a test can check."""
    assert M.PET_RATE is PR.INCIDENCE_RATE


def test_the_historical_rate_is_kept_as_history_and_is_not_the_active_one() -> None:
    """John's §3: 56.8 % (commonly rounded to 57 %) is retained as PROVENANCE, never as the
    multiplier. The record carries the edition and the reference date it was measured at, which
    is what makes it history rather than a number somebody deleted."""
    assert PR.HISTORICAL["incidence_rate"] == 0.568
    assert PR.HISTORICAL["source_edition"] == "2017–2018"
    assert PR.HISTORICAL["reference_period"] == "2016-12-31"
    assert PR.HISTORICAL["rounded_as_used"] == 0.57
    assert PR.HISTORICAL["incidence_rate"] != PR.INCIDENCE_RATE


def test_the_two_published_avma_figures_agree_with_each_other() -> None:
    """The Sourcebook publishes BOTH the rate and the count of pet-owning households, and the
    consistency of the two is a check on the citation rather than a derivation: 77.5 million at
    58.6 % implies about 132.25 million U.S. households, which is the ACS household count for the
    period. Encoded here so the citation cannot drift from its own arithmetic."""
    implied = PR.PET_OWNING_HOUSEHOLDS / PR.INCIDENCE_RATE
    assert 132_000_000 < implied < 132_500_000


def test_provenance_reads_the_vintage_and_the_version_it_is_given() -> None:
    """`household_vintage` and `methodology_version` are the two fields that are NOT this module's
    to state: the first is whichever ACS release is active in THIS database and the second is the
    formula version the pipeline stamps. Typing either here would be a second copy of a fact the
    system already holds, which is the whole defect this task removes."""
    p = PR.provenance(household_vintage="2019–2023", methodology_version="v1")
    assert p["household_vintage"] == "2019–2023"
    assert p["methodology_version"] == "v1"
    other = PR.provenance(household_vintage="2020–2024", methodology_version="v2")
    assert other["household_vintage"] == "2020–2024" and other["methodology_version"] == "v2"


def test_provenance_carries_every_field_john_named() -> None:
    """His §6 list, plus CONTROLLER RULING (1)'s `methodology_note` and nothing else. The set is
    pinned both ways so a field cannot be quietly dropped or quietly added."""
    p = PR.provenance(household_vintage="2019–2023", methodology_version="v1")
    assert set(p) == {
        "source", "source_dataset", "source_edition", "reference_period", "incidence_rate",
        "incidence_rate_display", "rate_geography", "household_source", "household_vintage",
        "derivation", "status", "methodology_version", "methodology_note", "licence_status",
    }
    assert p["source"] == "American Veterinary Medical Association"
    assert p["source_dataset"] == "Pet Ownership and Demographics Sourcebook"
    assert p["source_edition"] == "2025"
    assert p["reference_period"] == "2025"
    assert p["incidence_rate"] == 0.586
    assert p["incidence_rate_display"] == "58.6%"
    assert p["rate_geography"] == "United States"
    assert p["household_source"] == "U.S. Census Bureau, American Community Survey 5-Year Estimates"
    assert p["derivation"] == "local Census households × national AVMA pet-household incidence rate"
    assert p["status"] == "ESTIMATED"


def test_the_provenance_carries_the_sourcebooks_own_methodology_sentence() -> None:
    """CONTROLLER RULING (1). John ruled `reference_period: "2025"`; the Sourcebook's own
    Introduction says the findings draw on surveys conducted in 2023, 2024 AND 2025. His value
    stands and the note sits beside it, so the record is never less precise than the source it
    cites."""
    note = PR.provenance(household_vintage="2019–2023", methodology_version="v1")["methodology_note"]
    assert "conducted in 2023, 2024, and 2025" in note
    assert "6,979 respondents" in note and "7,539" in note and "7,519" in note
    assert "weighted based on certain demographic and other variables" in note


def test_the_licence_status_is_the_unresolved_one_and_says_both_halves() -> None:
    """CONTROLLER RULING (4). The Sourcebook's own copyright page prohibits reproduction without
    written permission, so the source is VERIFIED and the redistribution right is NOT. The string
    the registry row and the API both carry is this one, never a composed variant."""
    assert PR.LICENCE_STATUS == "SOURCE VERIFIED / LICENCE-REDISTRIBUTION UNRESOLVED"
    assert PR.provenance(household_vintage="2019–2023", methodology_version="v1")["licence_status"] == PR.LICENCE_STATUS


def test_the_derivation_reads_the_one_rate_rather_than_a_number_of_its_own() -> None:
    """`pet_households_est` is the single derivation (geo_metric and materialize both call it).
    The expected value is COMPUTED from the module constant, so this case moves with the rate
    instead of pinning a number that has to be hand-edited every time the source is re-cited —
    which is what let `0.57` sit unexplained for a year."""
    assert M.pet_households_est(27600) == round(27600 * PR.INCIDENCE_RATE)
    assert M.pet_households_est(27600) == 16174
    assert M.pet_households_est(None) is None
    assert "placeholder" not in (M.pet_households_est.__doc__ or "")


def test_the_layer_caveat_is_composed_from_the_provenance_and_calls_it_nothing_else() -> None:
    """The served caveat for the pets layer. It names the source, the edition and the rate, says
    the local figure is derived, and says the national rate does not establish the local one
    (John's §5). "placeholder" is gone: the rate is the approved AVMA figure now, and a caveat
    that still called it a placeholder would be the old provenance defect in the copy."""
    from app.api.market import PETS_CAVEAT

    assert PR.SOURCE in PETS_CAVEAT
    assert PR.SOURCE_EDITION in PETS_CAVEAT and PR.SOURCE_DATASET in PETS_CAVEAT
    assert PR.INCIDENCE_RATE_DISPLAY in PETS_CAVEAT
    assert "placeholder" not in PETS_CAVEAT
    assert "not an observed count" in PETS_CAVEAT
    assert "does not establish" in PETS_CAVEAT


def test_the_integration_contract_quotes_the_caveat_this_module_composes() -> None:
    """The contract document (`docs/integrations/market-data-api.md`) shows the `/api/layers`
    payload for a reader building against it, and it printed the caveat by hand. A doc that
    quotes a string the code composes has to be pinned to it or it drifts — `test_contract_doc.py`
    pins every other fact in that file the same way."""
    from pathlib import Path

    from app.api.market import PETS_CAVEAT

    doc = Path(__file__).resolve().parents[2] / "docs" / "integrations" / "market-data-api.md"
    assert PETS_CAVEAT in doc.read_text(encoding="utf-8")


def test_the_registry_keeps_the_statistic_the_publication_and_the_feed_apart(conn) -> None:
    """CONTROLLER RULING (4), the registry half. Three different things were one row:

      (a) the single cited national statistic — used, attributed, redistribution unresolved;
      (b) the Sourcebook publication — never redistributed, no extract stored or shipped;
      (c) the per-geography licensed incidence FEED — `blocked`, unchanged, not in use.

    The old `pet_ownership` note ("Ship only the ACS-derived estimate (rate 0.57) until a licence
    is signed") conflated (a) with (c): it described the feed's row while giving the operating
    instruction for the statistic, and named a rate that is no longer the one in use. (a) is now
    its own row, so the admin Data Sources tab shows the statistic's own status instead of
    inferring it from a blocked feed's note."""
    with conn.cursor() as cur:
        cur.execute("SELECT license_status, notes, attribution_text, display_name FROM dataset_registry WHERE dataset_key = 'avma_pet_rate'")
        row = cur.fetchone()
    assert row is not None, "the cited national statistic has no registry row of its own"
    status, notes, attribution, display = row
    # (a): used, so not `blocked`; redistribution not established, so not `cleared`.
    assert status == "unresolved"
    assert PR.LICENCE_STATUS in notes
    assert PR.SOURCE in attribution and PR.SOURCE_EDITION in attribution
    assert "Sourcebook" in display
    # (b): the publication itself is named as NOT redistributed, in the row that cites it.
    assert "no table, figure or page" in notes


def test_the_blocked_per_geography_feed_is_still_blocked_and_no_longer_carries_the_old_rate(conn) -> None:
    """CONTROLLER RULING (4): "Do NOT turn the pet layer off" — and equally, do not quietly clear
    the feed. `pet_ownership` is the LICENSED per-geography incidence feed and stays `blocked`,
    with a note that now describes only itself."""
    with conn.cursor() as cur:
        cur.execute("SELECT license_status, notes FROM dataset_registry WHERE dataset_key = 'pet_ownership'")
        status, notes = cur.fetchone()
    assert status == "blocked"
    assert "0.57" not in notes
    assert "avma_pet_rate" in notes, "the feed's note must point at the row that carries the statistic it is NOT"


def test_the_pets_class_breaks_are_the_households_breaks_through_the_rate() -> None:
    """CONTROLLER RULING (3) — `AREA_LAYERS.pets` was cut at 0.57 and has to be RE-DERIVED.

    `scripts/measure_area_breaks.py` reads the SERVED distribution out of `geo_metric`, and the
    pets layer's served rows are exactly the households layer's: `geo_metric._pets` walks
    `_tract_households` — the same cached scan `_households` walks — writes one row per tract,
    inherits that row's suppression, and computes `round(hh x rate)`, which is `None` only where
    `hh` is. So the two served SETS are identical and pets is a MONOTONE transform of households.

    That makes the re-derivation exact rather than a scaling: sorting by pets is sorting by
    households, and the script's positional `quantile` therefore satisfies

        quantile(pets, p) == round(quantile(households, p) x rate)

    for every p. This pins that identity with the script's OWN function, so the new breaks can be
    re-derived from the households measurement of record (QA, 2026-09-12, in the script's own
    docstring: 83,783 served, p25 1,054, p50 1,446, p75 1,897) without a second national load —
    which is what this environment cannot do, `CENSUS_API_KEY` being worker-only.

    The numbers it produces at 0.586 are p25 618, p50 847, p75 1,112, which round to the SAME
    legend-readable breaks the table already carries ([600, 850, 1100]) under the rounding the
    table itself used at 0.57 (601 -> 600, 824 -> 850, 1,081 -> 1,100). The table does not move;
    the COMMENT that records how it was cut does, because it names a rate that is no longer used.
    """
    import importlib.util
    import pathlib
    import random

    spec = importlib.util.spec_from_file_location(
        "measure_area_breaks", pathlib.Path(__file__).resolve().parents[2] / "scripts" / "measure_area_breaks.py"
    )
    assert spec and spec.loader
    mab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mab)

    rng = random.Random(20260915)
    households = sorted(float(rng.randrange(0, 6000)) for _ in range(4000))
    for rate in (PR.INCIDENCE_RATE, PR.HISTORICAL["rounded_as_used"]):
        pets = sorted(float(M.pet_households_est(h)) for h in households)
        # The transform is monotone, so the sorted pets list IS the sorted households list mapped.
        assert pets == [float(round(h * rate)) for h in households] or rate != PR.INCIDENCE_RATE
        for p in (0.25, 0.5, 0.75, 0.9):
            assert mab.quantile([float(round(h * rate)) for h in households], p) == round(mab.quantile(households, p) * rate)

    # The measurement of record, carried through the identity above.
    recorded = {0.25: 1054, 0.5: 1446, 0.75: 1897}
    assert [round(v * PR.INCIDENCE_RATE) for v in recorded.values()] == [618, 847, 1112]
    assert [round(v * PR.HISTORICAL["rounded_as_used"]) for v in recorded.values()] == [601, 824, 1081]
