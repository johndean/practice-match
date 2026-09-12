"""The one place the United States is enumerated.

Before 2026-09-12 this programme carried TWO hand-kept six-entry lists of states -- `market_state`,
seeded by `migrations/017_census_registry.sql` with 48/06/12/13/36/08, and `STATE_FIPS` in
`app/census/geocode.py`, the same six again. Every loader (`scripts/census_load.py`,
`app/tasks/census.py`, `app/census/geo_metric.py`) reads the first to decide what to fetch, and the
geocoder's place-fallback rung reads the second, so a practice in any of the other forty-five
states loaded no boundaries, no ACS rows and no metrics, and skipped a fallback rung entirely.

Both are now derived from `STATES` below, which is the complete set: fifty states and the District
of Columbia. It is deliberately NOT a subset that grows as markets are added -- a listing in any US
state must work with no code change, which is the whole point of removing the other two lists.

Territories (PR 72, VI 78, GU 66, AS 60, MP 69) are OUT, and that is a data decision rather than an
oversight: the ACS 5-year detailed tables this programme reads do not publish `B19013_001E` for
them on the same `state:*` geography, and TIGER's tract files for the island areas are published
under separate vintages. Adding one is a one-line change here plus a `market_state` row.
"""
from __future__ import annotations

#: (USPS abbreviation, two-digit FIPS, name). FIPS order, which is how `market_state` sorts.
STATES: tuple[tuple[str, str, str], ...] = (
    ("AL", "01", "Alabama"), ("AK", "02", "Alaska"), ("AZ", "04", "Arizona"), ("AR", "05", "Arkansas"),
    ("CA", "06", "California"), ("CO", "08", "Colorado"), ("CT", "09", "Connecticut"), ("DE", "10", "Delaware"),
    ("DC", "11", "District of Columbia"), ("FL", "12", "Florida"), ("GA", "13", "Georgia"), ("HI", "15", "Hawaii"),
    ("ID", "16", "Idaho"), ("IL", "17", "Illinois"), ("IN", "18", "Indiana"), ("IA", "19", "Iowa"),
    ("KS", "20", "Kansas"), ("KY", "21", "Kentucky"), ("LA", "22", "Louisiana"), ("ME", "23", "Maine"),
    ("MD", "24", "Maryland"), ("MA", "25", "Massachusetts"), ("MI", "26", "Michigan"), ("MN", "27", "Minnesota"),
    ("MS", "28", "Mississippi"), ("MO", "29", "Missouri"), ("MT", "30", "Montana"), ("NE", "31", "Nebraska"),
    ("NV", "32", "Nevada"), ("NH", "33", "New Hampshire"), ("NJ", "34", "New Jersey"), ("NM", "35", "New Mexico"),
    ("NY", "36", "New York"), ("NC", "37", "North Carolina"), ("ND", "38", "North Dakota"), ("OH", "39", "Ohio"),
    ("OK", "40", "Oklahoma"), ("OR", "41", "Oregon"), ("PA", "42", "Pennsylvania"), ("RI", "44", "Rhode Island"),
    ("SC", "45", "South Carolina"), ("SD", "46", "South Dakota"), ("TN", "47", "Tennessee"), ("TX", "48", "Texas"),
    ("UT", "49", "Utah"), ("VT", "50", "Vermont"), ("VA", "51", "Virginia"), ("WA", "53", "Washington"),
    ("WV", "54", "West Virginia"), ("WI", "55", "Wisconsin"), ("WY", "56", "Wyoming"),
)

#: USPS abbreviation -> two-digit FIPS. `app/census/geocode.py` filters `geo_area.state_fips`
#: against this directly, so it must carry every state the programme can be handed a listing in.
FIPS_BY_ABBR: dict[str, str] = {abbr: fips for abbr, fips, _name in STATES}
