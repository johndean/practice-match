"""The pet-household incidence rate, and the provenance that makes it a citation.

Task PET-RATE-PROVENANCE (John's requirement of 2026-09-15). Until this module the rate was a
bare `0.57` in `metrics.py` whose only explanation was the word "placeholder" in its own comment,
and `frontend/src/logic.js` carried a second, independent copy of the same literal. Two copies of
an unexplained number is how a product comes to state a figure nobody can trace.

WHAT THE NUMBER IS. `estimated_pet_households = local Census households x this rate`. The
households are the Census's own ACS estimate for a real area; the rate is a NATIONAL survey
incidence from the AVMA. The product therefore never has a Census-observed local pet-household
count and must never present one: the result is DERIVED, and `status` says so in every record
this module produces.

WHAT THE NUMBER IS NOT. It is not a local rate. Applying a national incidence to a local
household count says nothing about how many households in THAT market keep pets; it says what
that market would hold if it behaved like the country. The AVMA publishes no tract, ZIP, county
or metro pet-household count that this product has licensed, loaded or verified, and nothing here
may imply otherwise (`dataset_registry.pet_ownership` stays `blocked` for exactly that feed).

LICENSING. The Sourcebook's own copyright page prohibits reproduction or transmission in any form
without the AVMA's written permission. The single cited national statistic, its edition, its
reference period and an attribution are what this product carries; no table, figure or page of the
Sourcebook is stored or shipped. `LICENCE_STATUS` records that split and is the one string the
`dataset_registry` row and the API both read.
"""

from __future__ import annotations

from typing import Any

# --- The approved source ---------------------------------------------------------------------
# American Veterinary Medical Association, 2025 Pet Ownership and Demographics Sourcebook
# (Veterinary Economics Division, AVMA; (c) 2025 AVMA; digital ISBN 979-8-9877127-8-8).
SOURCE = "American Veterinary Medical Association"
SOURCE_DATASET = "Pet Ownership and Demographics Sourcebook"
SOURCE_EDITION = "2025"

# John's ruling, verbatim: `reference_period` is "2025". See `METHODOLOGY_NOTE` below, which is
# the Sourcebook's own account of what that period draws on -- controller ruling (1), recorded
# because a provenance record must never be less precise than the source it cites.
REFERENCE_PERIOD = "2025"

#: U.S. households owning at least one pet, as published. THE ONE PRODUCTION RATE.
INCIDENCE_RATE: float = 0.586
#: The source's own rounding, which is what a caption prints -- never a format of the float.
INCIDENCE_RATE_DISPLAY = "58.6%"
#: The second figure the same edition publishes, kept so the citation can be checked against
#: itself: 77.5e6 / 0.586 = 132.25e6 U.S. households, the ACS count for the period.
PET_OWNING_HOUSEHOLDS = 77_500_000
#: The rate is a national survey incidence. It is not, and must not be presented as, a local one.
RATE_GEOGRAPHY = "United States"

HOUSEHOLD_SOURCE = "U.S. Census Bureau, American Community Survey 5-Year Estimates"
DERIVATION = "local Census households × national AVMA pet-household incidence rate"
#: Never "Pet households", which implies direct observation (John's §4).
STATUS = "ESTIMATED"

#: The Sourcebook's own Introduction, verbatim (controller ruling (1)). It is the source's
#: description of what the figure is, and it is the reason `REFERENCE_PERIOD` alone would be a
#: less precise record than the source: the findings draw on three survey years, not one.
METHODOLOGY_NOTE = (
    "The findings are largely based on responses to the AVMA Pet Ownership and Demographics "
    "Surveys conducted in 2023, 2024, and 2025 and include pet owner behaviors during the "
    "previous calendar year. A total of 6,979 respondents completed the survey in 2023, 7,539 "
    "completed it in 2024, and 7,519 completed it in 2025. Results have been weighted based on "
    "certain demographic and other variables to match their distribution in the U.S. population "
    "and household information reported by the U.S. Census Bureau at the time of publication."
)

#: Controller ruling (4). The statistic is verified against the published edition; the right to
#: redistribute the Sourcebook is not established and is not assumed. One string, read by the
#: `dataset_registry` row and by the served provenance, so the two can never say different things.
LICENCE_STATUS = "SOURCE VERIFIED / LICENCE-REDISTRIBUTION UNRESOLVED"

#: What the product used before 2026-09-15, kept as HISTORY and never as a multiplier (John's §3).
#: `rounded_as_used` is the value the code actually carried: the 2017-2018 edition reports 56.8 %
#: at year-end 2016 and the constant was written as the rounded 0.57, so both are recorded --
#: the figure the source published and the figure this product computed with.
HISTORICAL: dict[str, Any] = {
    "source": SOURCE,
    "source_dataset": "Pet Ownership & Demographics Sourcebook",
    "source_edition": "2017–2018",
    "reference_period": "2016-12-31",
    "incidence_rate": 0.568,
    "rounded_as_used": 0.57,
    "retired_on": "2026-09-15",
    "retired_because": "superseded by the 2025 edition; retained as provenance and audit history only",
}


def provenance(*, household_vintage: str | None, methodology_version: str) -> dict[str, Any]:
    """The whole record for one derived pet-household figure, in John's own §6 field order.

    The two arguments are the fields this module must NOT state. `household_vintage` is whichever
    ACS release is active in the database being served (`active_vintage.acs5`) and
    `methodology_version` is the formula version the pipeline stamps on the row
    (`metrics.FORMULA_VERSION`); typing either here would put a second copy of a fact the system
    already holds beside the one it keeps, which is the defect this whole module removes.
    """
    return {
        "source": SOURCE,
        "source_dataset": SOURCE_DATASET,
        "source_edition": SOURCE_EDITION,
        "reference_period": REFERENCE_PERIOD,
        "incidence_rate": INCIDENCE_RATE,
        "incidence_rate_display": INCIDENCE_RATE_DISPLAY,
        "rate_geography": RATE_GEOGRAPHY,
        "household_source": HOUSEHOLD_SOURCE,
        "household_vintage": household_vintage,
        "derivation": DERIVATION,
        "status": STATUS,
        "methodology_version": methodology_version,
        "methodology_note": METHODOLOGY_NOTE,
        "licence_status": LICENCE_STATUS,
    }
