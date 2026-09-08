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


def test_load_writes_rows_and_a_succeeded_run(conn):
    def handler(r: httpx.Request):
        if "for=tract" in str(r.url):
            return httpx.Response(200, json=FIX)
        # every other geography: one row with the same columns, minimal
        hdr = FIX[0][:-3] + (["state", "county"] if "county:*" in str(r.url) else ["state", "place"] if "place" in str(r.url)
                              else ["state"] if "for=state" in str(r.url) else ["metropolitan statistical area/micropolitan statistical area"] if "metropolitan" in str(r.url) else ["us"])
        vals = ["X", "10", "1", "5", "1", "50000", "100", "30000", "40.0", "3", "6"] + (["48", "001"] if len(hdr) == 13 and hdr[-1] == "county" else ["48", "00001"] if hdr[-1] == "place" else ["48"] if hdr[-1] == "state" else ["12420"] if "metropolitan" in hdr[-1] else ["1"])
        return httpx.Response(200, json=[hdr, vals])
    reg = load_registry(conn)

    def factory(ds):
        return CensusClient("K", ds, None, transport=httpx.MockTransport(handler), contact=CONTACT)

    written = acs.load(conn, factory, "acs5", ["48"])
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM acs_measure WHERE summary_level='140' AND vintage=%s", (reg["acs5"].vintage,))
        assert cur.fetchone()[0] == 2 * 7  # two tracts x seven estimate variables (see test above)
        cur.execute("SELECT estimate, moe FROM acs_measure WHERE geo_id='48453000102' AND variable='B01003_001E'")
        assert cur.fetchone() == (None, None)
        cur.execute("SELECT status, rows_written FROM ingest_run WHERE dataset_key='acs5' ORDER BY id DESC LIMIT 1")
        status, rows = cur.fetchone()
    assert status == "succeeded" and rows == written > 16


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
