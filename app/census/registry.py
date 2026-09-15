"""Read side of dataset_registry. Attribution strings and licence status come from
the database (spec §12) so a terms change propagates in one UPDATE."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import psycopg2.extensions

COLUMNS = ("dataset_key", "display_name", "api_dataset_id", "base_url", "vintage", "naics_param", "refresh_cadence",
           "license_status", "license_name", "license_url", "attribution_text", "last_verified_at", "notes")


@dataclass(frozen=True)
class Dataset:
    dataset_key: str
    display_name: str
    api_dataset_id: str | None
    base_url: str
    vintage: str
    naics_param: str | None
    refresh_cadence: str
    license_status: str
    license_name: str | None
    license_url: str | None
    attribution_text: str
    last_verified_at: datetime | None
    notes: str | None

    @property
    def cleared(self) -> bool:
        return self.license_status == "cleared"


def load(conn: psycopg2.extensions.connection) -> dict[str, Dataset]:
    with conn.cursor() as cur:
        cur.execute(f"SELECT {', '.join(COLUMNS)} FROM dataset_registry ORDER BY dataset_key")
        return {row[0]: Dataset(*row) for row in cur.fetchall()}


def is_cleared(conn: psycopg2.extensions.connection, dataset_key: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT license_status = 'cleared' FROM dataset_registry WHERE dataset_key = %s", (dataset_key,))
        row = cur.fetchone()
        return bool(row and row[0])


def attribution(conn: psycopg2.extensions.connection, dataset_keys: list[str]) -> list[str]:
    """Attribution lines in the order requested; unknown keys are skipped, not invented."""
    if not dataset_keys:
        return []
    with conn.cursor() as cur:
        cur.execute("SELECT dataset_key, attribution_text FROM dataset_registry WHERE dataset_key = ANY(%s)", (dataset_keys,))
        by_key = dict(cur.fetchall())
    return [by_key[k] for k in dataset_keys if k in by_key]


# ---------------------------------------------------------------------------------------
# The admin Data Sources tab's two measured layout budgets (A38, review I1 and F1, 2026-09-14).
#
# The tab prints `notes`, `license_name`, `refresh_cadence` and the vintages VERBATIM into the
# approved design's own table -- no truncation and no clamping, by ruling: this is the surface
# CLAUDE.md marks legally load-bearing and hidden text on a legal gate is not an option. So the
# fit is a property of the DATA, and these are where it is stated once for everything that has to
# hold it: `tests/census/test_registry.py`'s pin, `app/api/admin_data_sources.py`'s write door and
# `scripts/measure_source_subline_cap.py`'s re-derivation all import from here.
#
# MEASURED in real Chromium at the design's own 1440 x 940, with the design's own three
# stylesheets and the app's own markup (`App.vue`'s admin table, grid `1.1fr 1.6fr .8fr .8fr`,
# `gap: 20px`, row `padding: 16px 20px`, card `max-width: 1180px`). The design's own five fixture
# rows are 75, 94, 75, 94 and 93 px; its tallest is 94 px, and that row's cells are ONE line of
# main plus TWO lines of sub-line. Two lines is therefore the budget, in both columns.
#
#   * Source column   376 px -- probing the composed sub-line at word lengths 4-12 the first to
#                     need a third line was 120 characters; behind the registry's own longest
#                     `license_name` (57 characters) at word lengths 5-22 nothing went over two
#                     lines to 120. 115 is the floor under both probes.
#   * Dataset column  258 px -- the same probe at word lengths 4-16 (the range this sub-line's own
#                     vocabulary spans; its longest token is `Current_Current`, 15) first went over
#                     at 80 characters. 78 is the floor. 22-letter words fall to 70 and are
#                     excluded with that reason: no clause this sub-line composes has one.
#
# `scripts/measure_source_subline_cap.py` re-runs the browser probe and fails if either number has
# moved, the way `scripts/measure_area_breaks.py` re-derives `AREA_LAYERS`.
SOURCE_SUBLINE_CAP = 115
DATASET_SUBLINE_CAP = 78

# What the quarterly sweep appends to a flagged row's Source sub-line
# (`frontend/src/admin/data_sources.ts`). Counted for every row the sweep CAN reach -- which is
# every row with a `license_url`, `app/census/license.py`'s own `WHERE` -- because a note that
# fits only until its terms page is edited does not fit.
DRIFT_CLAUSE = " · Terms drift flagged"

# The rows whose `notes` carry a LEGAL citation and may therefore wrap past the cap (controller
# ruling, review F2, 2026-09-14): legally material text is never shortened to fit a layout. Keyed
# by `dataset_key`, valued by the reason, which is printed when the pin reports.
LEGAL_NOTE_ROWS = {
    "practice_locations": "legal citation, may wrap: names the blocked 2017 Google Places export (plan D15) and the Google Maps Platform terms that forbid storing or rendering it",
    "google_places_aggregate": "legal citation, may wrap: names the Service Specific Terms §13 condition the row is blocked on",
}

# Values `dataset_registry.vintage` and `active_vintage.vintage` hold where the dataset HAS no
# vintage: placeholders and machine identifiers, never something anyone declared (review F10).
# `vintage` is NOT NULL (017:14), so without this the tab printed "Declared vintage n/a" on a
# blocked row and "Declared vintage Current_Current" -- the Census Geocoder's benchmark identifier
# -- on another. The design prints no vintage clause for these.
PLACEHOLDER_VINTAGES = ("n/a", "live", "TBD", "Current_Current", "latest", "latest quarter", "monthly release")

# 017's own `refresh_cadence` vocabulary (review F7 / M9): the column is free text and the tab
# prints it verbatim as the sub-line's first clause, so a second spelling of one cadence ("Live
# tiles" beside "live") reads as two different things.
REFRESH_CADENCES = ("Annual", "Annual (Apr)", "Annual (Dec)", "Monthly", "On write", "Quarterly", "Static", "live", "n/a")
