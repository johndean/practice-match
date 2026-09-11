"""ACS 5-year loads (task A5 brief; spec §2 acs5/acs5_subject/acs5_prior, §4 variables, §6
levels). Adapted from the brief's illustrative code to the client interface A3's review round
actually committed (controller amendment A-C3b): `CensusClient` is built with a required
`contact` kwarg (M3) and is used as a context manager (m3); `fetch_table` takes the raw
`(get, for_, expected, in_)` parameters and validates internally (m5) -- there is no separate
`build_url`/`validate_variables` call for `acs.load` to make.
"""
import json
from pathlib import Path

import httpx
import pytest

from app.census import acs
from app.census.client import CensusClient
from app.census.registry import load as load_registry

FIX = json.loads((Path(__file__).parent / "fixtures" / "acs_tract_48.json").read_text())
CONTACT = "contact@vinfoundation.org"


def test_variable_lists_are_the_spec_map():
    assert acs.VARIABLES["acs5"] == ["B01003_001E", "B01003_001M", "B11001_001E", "B11001_001M", "B19013_001E", "B19013_001M",
                                     "B19301_001E", "B01002_001E", "B25003_002E", "B25001_001E"]
    assert acs.VARIABLES["acs5_subject"] == ["S1501_C02_015E"]
    assert acs.VARIABLES["acs5_prior"] == ["B01003_001E", "B01003_001M"]


def test_geographies_cover_spec_levels_for_each_state_plus_cbsa_and_nation():
    g = acs.GEOGRAPHIES(["48", "06"])
    levels = [(x.summary_level, x.for_, x.in_) for x in g]
    assert ("140", "tract:*", "state:48") in levels and ("140", "tract:*", "state:06") in levels
    assert ("160", "place:*", "state:48") in levels
    assert ("050", "county:*", "state:48") in levels
    assert ("040", "state:48", None) in levels
    assert ("310", "metropolitan statistical area/micropolitan statistical area:*", None) in levels
    assert ("010", "us:1", None) in levels
    assert levels.count(("310", "metropolitan statistical area/micropolitan statistical area:*", None)) == 1


def test_geoid_assembly_per_level():
    assert acs.geoid({"state": "48", "county": "453", "tract": "000101"}, "140") == "48453000101"
    assert acs.geoid({"state": "48", "place": "05000"}, "160") == "4805000"
    assert acs.geoid({"state": "48", "county": "453"}, "050") == "48453"
    assert acs.geoid({"state": "48"}, "040") == "48"
    assert acs.geoid({"metropolitan statistical area/micropolitan statistical area": "12420"}, "310") == "12420"
    assert acs.geoid({"us": "1"}, "010") == "1"


def test_geoid_raises_for_an_unknown_summary_level():
    with pytest.raises(ValueError):
        acs.geoid({"state": "48"}, "150")


def test_geoid_raises_when_the_row_lacks_the_identifier_the_level_needs():
    with pytest.raises(ValueError):
        acs.geoid({"state": "48"}, "140")  # no county/tract


def test_num_returns_none_for_a_value_that_is_not_a_valid_decimal():
    """Every sentinel is already folded to `None` by `CensusClient.normalise()` before a row
    ever reaches `to_measures`, but `_num` still guards against a genuinely malformed value
    reaching `Decimal()` rather than propagating a raw `decimal.InvalidOperation`."""
    assert acs._num(None) is None
    assert acs._num("not-a-number") is None
    assert acs._num("4321") == 4321


def test_to_measures_pairs_estimates_with_moe_and_keeps_nulls():
    header, *rows = FIX
    dicts = [dict(zip(header, r)) for r in rows]
    dicts[1]["B01003_001E"] = None
    dicts[1]["B01003_001M"] = None  # what the client's sentinel pass produces
    ms = {(m.geo_id, m.variable): m for m in acs.to_measures(dicts, acs.VARIABLES["acs5"], "140")}
    assert ms[("48453000101", "B01003_001E")].estimate == 4321 and ms[("48453000101", "B01003_001E")].moe == 210
    assert ms[("48453000101", "B19013_001E")].moe == 9100
    assert ms[("48453000101", "B19301_001E")].moe is None          # no MOE requested for per-capita income
    assert ms[("48453000102", "B01003_001E")].estimate is None and ms[("48453000102", "B01003_001E")].moe is None
    assert ("48453000101", "B01003_001M") not in ms                 # MOE columns are folded, not stored as variables
    # acs5's ten-entry variable list is three E/M pairs plus four E-only variables (per-capita
    # income, median age, renter-occupied units, total units) == seven estimate variables, not
    # ten and not eight -- pinned here so a future edit to VARIABLES["acs5"] cannot silently
    # change this count without a test noticing.
    assert len({v for v in acs.VARIABLES["acs5"] if v.endswith("E")}) == 7
    assert len(ms) == 2 * 7


def _full_state_handler():
    """One tract-level fixture pull (`FIX`) plus one minimal row for every other geography
    level `acs.GEOGRAPHIES` visits for state 48 -- shared by the write test and the idempotency
    test below (A5's review of itself)."""
    def handler(r: httpx.Request):
        if "for=tract" in str(r.url):
            return httpx.Response(200, json=FIX)
        # every other geography: one row with the same columns, minimal
        hdr = FIX[0][:-3] + (["state", "county"] if "county:*" in str(r.url) else ["state", "place"] if "place" in str(r.url)
                              else ["state"] if "for=state" in str(r.url) else ["zip code tabulation area"] if "tabulation" in str(r.url)
                              else ["metropolitan statistical area/micropolitan statistical area"] if "metropolitan" in str(r.url) else ["us"])
        vals = ["X", "10", "1", "5", "1", "50000", "100", "30000", "40.0", "3", "6"] + (["48", "001"] if len(hdr) == 13 and hdr[-1] == "county" else ["48", "00001"] if hdr[-1] == "place" else ["48"] if hdr[-1] == "state" else ["78704"] if "tabulation" in hdr[-1] else ["12420"] if "metropolitan" in hdr[-1] else ["1"])
        return httpx.Response(200, json=[hdr, vals])
    return handler


def test_load_writes_rows_and_a_succeeded_run(conn):
    reg = load_registry(conn)

    def factory(ds):
        return CensusClient("K", ds, None, transport=httpx.MockTransport(_full_state_handler()), contact=CONTACT)

    written = acs.load(conn, factory, "acs5", ["48"])
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM acs_measure WHERE summary_level='140' AND vintage=%s", (reg["acs5"].vintage,))
        assert cur.fetchone()[0] == 2 * 7  # two tracts x seven estimate variables (see test above)
        cur.execute("SELECT estimate, moe FROM acs_measure WHERE geo_id='48453000102' AND variable='B01003_001E'")
        assert cur.fetchone() == (None, None)
        cur.execute("SELECT status, rows_written FROM ingest_run WHERE dataset_key='acs5' ORDER BY id DESC LIMIT 1")
        status, rows = cur.fetchone()
    assert status == "succeeded" and rows == written > 16


def test_load_is_idempotent_on_a_rerun(conn):
    """A5's review of itself: re-running a load (an operator retry, or a scheduled reload of
    the same vintage) upserts, never duplicates -- `acs_measure`'s primary key
    (geo_id, summary_level, vintage, variable) and the UPSERT's `ON CONFLICT DO UPDATE` already
    guarantee this; this proves it end to end, the way `test_tiger.py
    ::test_upsert_is_idempotent_and_computes_centroid` proves the same property for `geo_area`."""
    def factory(ds):
        return CensusClient("K", ds, None, transport=httpx.MockTransport(_full_state_handler()), contact=CONTACT)

    first = acs.load(conn, factory, "acs5", ["48"])
    second = acs.load(conn, factory, "acs5", ["48"])
    assert first == second > 16  # every geography level, same convention as the write test above
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM acs_measure")
        assert cur.fetchone()[0] == first  # still the same total, not doubled
        cur.execute("SELECT count(*) FROM ingest_run WHERE dataset_key='acs5'")
        assert cur.fetchone()[0] == 2  # one ledger row per run, even though the data didn't grow


def test_load_refuses_a_dataset_that_is_not_cleared(conn):
    """The spec §1 licensing gate applies to loads, not just display: `pet_ownership` is seeded
    `blocked` (migrations/017_census_registry.sql) and must never reach the network."""
    def factory(ds):
        raise AssertionError("a blocked dataset must never build a client")

    with pytest.raises(PermissionError):
        acs.load(conn, factory, "pet_ownership", ["48"])


def test_load_aborts_and_records_the_run_when_a_response_is_missing_a_variable(conn):
    """A partial load never activates a vintage (global constraint ¶12): a response missing an
    expected variable raises `VariableMissing`, which `ingest.run` records as `aborted`, and no
    row from that dataset is written."""
    def handler(r: httpx.Request):
        return httpx.Response(200, json=[["NAME", "state"], ["nation", "1"]])  # every variable missing

    def factory(ds):
        return CensusClient("K", ds, None, transport=httpx.MockTransport(handler), contact=CONTACT)

    from app.census.client import VariableMissing

    with pytest.raises(VariableMissing):
        acs.load(conn, factory, "acs5", ["48"])
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM ingest_run WHERE dataset_key='acs5' ORDER BY id DESC LIMIT 1")
        assert cur.fetchone()[0] == "aborted"
        cur.execute("SELECT count(*) FROM acs_measure")
        assert cur.fetchone()[0] == 0


# --- D-NS4: ZCTA income is LOADED, never aggregated from tracts -------------------------------
# `metrics.weighted_median` is a household-weighted average of tract medians: it has no combined
# margin of error by construction, so a figure derived that way could never fail the CV test, and
# shading a metro's ZCTAs with values that can never be suppressed would hollow out D-C36, whose
# entire point is that the margin of error is shown and measured. So summary level `860` is
# loaded, not aggregated.

# The identifier columns each geography's own rows carry, keyed by the `for=` clause
# `GEOGRAPHIES` builds -- `geoid()` assembles the geo_id out of exactly these.
_IDENTIFIERS = {
    "tract:*": {"state": "48", "county": "453", "tract": "000101"},
    "place:*": {"state": "48", "place": "05000"},
    "county:*": {"state": "48", "county": "453"},
    "zip code tabulation area:*": {"zip code tabulation area": "78704"},
    "metropolitan statistical area/micropolitan statistical area:*": {
        "metropolitan statistical area/micropolitan statistical area": "12420"},
    "us:1": {"us": "1"},
}
# One plausible row of acs5 values, in `VARIABLES["acs5"]` order, so the median household income
# and ITS OWN margin can be read back out of `acs_measure`.
_VALUES = ["31000", "120", "14000", "60", "92150", "6420", "51000", "34.1", "5200", "15500"]


def _recording_factory(seen):
    """A real `CensusClient` over `httpx.MockTransport` -- the shape every other load test in this
    file uses -- recording the `for=`/`in=` pair of every request as the CLIENT built it, rather
    than the argument `load()` handed over, and answering each geography with one row carrying
    that geography's own identifier columns."""
    def handler(request: httpx.Request) -> httpx.Response:
        for_, in_ = request.url.params["for"], request.url.params.get("in")
        seen.append((for_, in_))
        ids = _IDENTIFIERS.get(for_, {"state": for_.split(":")[1]})   # `for=state:48` names itself
        header = ["NAME", *acs.VARIABLES["acs5"], *ids]
        return httpx.Response(200, json=[header, ["A place", *_VALUES, *ids.values()]])

    def factory(ds):
        return CensusClient("K", ds, None, transport=httpx.MockTransport(handler), contact=CONTACT)

    return factory


def test_geographies_carries_the_zcta_level_once_nationally():
    """Checked against the Census API's own geography list for the active acs5 vintage
    (`https://api.census.gov/data/2023/acs/acs5/geography.json`, which needs no key): the level is
    named `zip code tabulation area`, geoLevelDisplay `860`, and carries NO `requires` entry -- so
    the query is national. Issuing it per state would be six identical national pulls."""
    g = acs.GEOGRAPHIES(["48", "06"])
    zcta = [x for x in g if x.summary_level == "860"]
    assert len(zcta) == 1, "ZCTAs are not nested inside states in the ACS 5-year API for this vintage"
    assert zcta[0].for_ == "zip code tabulation area:*" == f"{acs.ZCTA_COL}:*"
    assert zcta[0].in_ is None
    # The six levels that were already there are untouched: three per state, in order...
    assert [x.summary_level for x in g if x.in_ is not None] == ["140", "160", "050", "140", "160", "050"]
    # ...and the national ones keep their order, with 860 ahead of the two that were already there.
    assert [x.summary_level for x in g if x.in_ is None] == ["040", "040", "860", "310", "010"]


def test_geoid_builds_a_zcta_id_from_the_apis_own_column_name():
    assert acs.geoid({"zip code tabulation area": "78704"}, "860") == "78704"
    with pytest.raises(ValueError, match="zip code tabulation area"):
        acs.geoid({"state": "48"}, "860")
    with pytest.raises(ValueError, match="999"):
        acs.geoid({}, "999")


def test_load_with_a_levels_filter_fetches_that_level_alone_and_still_records_an_ingest_run(conn):
    """`--levels 860` exists so the ZCTA level can be loaded on its own rather than re-running all
    six geographies for six states -- a national ZCTA pull is the largest single ACS page this
    pipeline issues. The run is recorded in `ingest_run` exactly as any other."""
    seen: list[tuple[str, str | None]] = []

    written = acs.load(conn, _recording_factory(seen), "acs5", ["48", "06"], levels=["860"])

    assert seen == [("zip code tabulation area:*", None)], "a level filter must not fetch the other geographies"
    assert written > 0
    with conn.cursor() as cur:
        cur.execute("SELECT geo_id, summary_level FROM acs_measure WHERE variable = 'B19013_001E'")
        assert cur.fetchall() == [("78704", "860")]
        cur.execute("SELECT estimate, moe FROM acs_measure WHERE geo_id = '78704' AND variable = 'B19013_001E'")
        assert cur.fetchone() == (92150, 6420)   # the published estimate and ITS OWN margin, as loaded
        cur.execute("SELECT status, rows_written, request_count FROM ingest_run WHERE dataset_key='acs5' ORDER BY id DESC LIMIT 1")
        status, rows, requests = cur.fetchone()
    assert status == "succeeded" and rows == written
    assert requests == len(seen)   # derived from what was actually fetched, never a number typed here


def test_load_without_a_levels_filter_still_fetches_every_geography(conn):
    """The filter must not change the existing load when it is omitted. Proved by reading the
    geography list back out of `GEOGRAPHIES` -- order and all -- rather than by asserting a count
    typed into this test, which would pass a load that fetched the right NUMBER of wrong things."""
    seen: list[tuple[str, str | None]] = []

    acs.load(conn, _recording_factory(seen), "acs5", ["48"])

    assert seen == [(g.for_, g.in_) for g in acs.GEOGRAPHIES(["48"])]
    assert ("zip code tabulation area:*", None) in seen


def test_load_with_a_levels_filter_that_matches_nothing_fetches_nothing(conn):
    """The empty arm of the same branch. A filter that names a level `GEOGRAPHIES` does not carry
    -- an operator's typo -- fetches nothing, writes nothing, and still leaves a `succeeded` run
    behind saying so; `census_load.py` prints its `0 measures`, so the typo announces itself."""
    seen: list[tuple[str, str | None]] = []

    written = acs.load(conn, _recording_factory(seen), "acs5", ["48"], levels=["150"])

    assert seen == [] and written == 0
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM acs_measure")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT status, rows_written FROM ingest_run WHERE dataset_key='acs5' ORDER BY id DESC LIMIT 1")
        assert cur.fetchone() == ("succeeded", 0)
