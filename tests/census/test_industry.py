"""Industry loads (task A6 brief; spec §2 cbp/zbp/qwi/bds, §5 NAICS, §9 QWI's 20-quarter window).
Adapted from the brief's illustrative test code to the client interface A3's review round
actually committed (controller amendment A-C5, as `tests/census/test_acs.py` already is):
`CensusClient` requires a `contact` kwarg (M3) -- the brief's own `factory_for` helper and its
`test_qwi_latest_available_walks_back_from_404s` construct a client without one, which raises
`ValueError` before a single request is made, so both are corrected here exactly as A5 corrected
the same class of illustrative-code drift in `acs.py`'s task brief."""
from __future__ import annotations

import httpx
import pytest

from app.census import bds, cbp, qwi, zbp
from app.census.client import CensusClient

CONTACT = "contact@vinfoundation.org"


def factory_for(handler):
    return lambda ds: CensusClient("K", ds, None, transport=httpx.MockTransport(handler), contact=CONTACT)


def test_cbp_uses_registry_naics_param_and_alias_and_stores_flags_verbatim(conn):
    urls = []

    def handler(r):
        urls.append(str(r.url))
        code = r.url.params["NAICS2017"]
        return httpx.Response(200, json=[["NAME", "ESTAB", "EMP", "PAYANN", "EMP_N", "PAYANN_N", "state", "county", "NAICS2017"],
                                         ["Travis County, Texas", "12", "410", "38500", None, None, "48", "453", code],
                                         ["Hays County, Texas", "3", None, "0", "G", "G", "48", "209", code]])
    written = cbp.load(conn, factory_for(handler), ["48"])
    assert written == 6  # 2 counties x 3 NAICS codes
    assert all("NAICS2017=" in u for u in urls) and any("NAICS2017=453910" in u for u in urls) and not any("459910" in u for u in urls)
    with conn.cursor() as cur:
        cur.execute("SELECT naics_code, establishments, employment, annual_payroll_k, flag FROM cbp_industry WHERE geo_id='48209' ORDER BY naics_code")
        rows = cur.fetchall()
    # stored under the spec's code (459910) even though requested as the 2017 alias
    assert [r[0] for r in rows] == ["459910", "541940", "812910"]
    # A-C6: CBP uses noise infusion (EMP_N/PAYANN_N), not withheld cells -- a noise-range flag
    # does not itself null a value; a genuinely absent/sentinel EMP does, and the flag is kept
    # verbatim either way (§14).
    assert rows[1] == ("541940", 3, None, 0, "EMP_N=G;PAYANN_N=G")
    with conn.cursor() as cur:
        cur.execute("SELECT establishments, employment, annual_payroll_k, flag FROM cbp_industry WHERE geo_id='48453' AND naics_code='541940'")
        assert cur.fetchone() == (12, 410, 38500, None)


def test_cbp_county_geo_id_raises_when_the_row_lacks_state_or_county():
    """mypy narrowing (strict mode) needed `_county_geo_id` to bind `state`/`county` to locals
    before concatenating them, the same way `acs.geoid`'s `field()` closure does -- this proves
    the guard it added actually fires, mirroring `test_acs.py
    ::test_geoid_raises_when_the_row_lacks_the_identifier_the_level_needs`."""
    with pytest.raises(ValueError):
        cbp._county_geo_id({"state": "48"})


def test_cbp_refuses_a_dataset_that_is_not_cleared(conn):
    """The spec §1 licensing gate applies to every load, not just ACS (`tests/census/test_acs.py
    ::test_load_refuses_a_dataset_that_is_not_cleared`) -- cbp seeds `cleared`
    (migrations/017_census_registry.sql), so the blocked case is exercised by flipping the
    registry row directly, the same way a real licence decision (A9) would."""
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'blocked' WHERE dataset_key = 'cbp'")

    def factory(ds):
        raise AssertionError("a blocked dataset must never build a client")

    with pytest.raises(PermissionError):
        cbp.load(conn, factory, ["48"])


def _seed_zctas(conn, *zips, vintage="2023"):
    """Minimal `geo_area` rows for the ZCTAs (summary level `860`) A4's TIGER load would have
    bounded -- geometry columns are nullable and irrelevant to `zbp`'s own containment check."""
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO geo_area (geo_id, summary_level, vintage, name) VALUES (%s, '860', %s, %s)",
            [(z, vintage, f"ZCTA5 {z}") for z in zips],
        )


def test_zbp_loads_zip_establishments_once_per_naics_code_via_cbp_zip_code_geography(conn):
    """A-C6: `zbp` is served through the CBP endpoint's own `zip code` geography -- one request
    per NAICS code (three total, no per-state loop, no `in=`), keyed by `ZIPCODE`, and only ZIPs
    already bounded in `geo_area` (D11's ZIP≈ZCTA approximation) are kept; `10001` was never seen
    by the TIGER load for these market states and must be dropped."""
    _seed_zctas(conn, "78613", "78664")
    urls = []

    def handler(r):
        urls.append(str(r.url))
        code = r.url.params["NAICS2017"]
        return httpx.Response(200, json=[["ZIPCODE", "ESTAB", "NAICS2017"],
                                         ["78613", "7", code], ["78664", "2", code], ["10001", "99", code]])
    assert zbp.load(conn, factory_for(handler), ["48"]) == 8  # 2 in-bounds ZIPs x 4 NAICS keys
    assert len(urls) == 4
    assert all("for=zip%20code:*" in u and "in=" not in u for u in urls)
    assert any("NAICS2017=453910" in u for u in urls) and not any("459910" in u for u in urls)
    # The ALL-INDUSTRY total, `00`, loaded in the same pass (review round 1, Important 3). It is
    # the only way to tell "this ZIP has fewer than three veterinary establishments, and the
    # Census therefore publishes no count for that category" from "ZIP Code Business Patterns
    # does not cover this ZIP at all" -- the Census's own rule is that a category under three
    # establishments is not reported but IS counted in the sum total, so the total is the
    # universe and the absence of a 541940 row inside it is the withholding.
    assert any("NAICS2017=00" in u for u in urls)
    with conn.cursor() as cur:
        cur.execute("SELECT establishments FROM zbp_industry WHERE geo_id='78613' AND naics_code='00'")
        assert cur.fetchone() == (7,), "the all-industry total is stored under its own NAICS key"
    with conn.cursor() as cur:
        cur.execute("SELECT establishments FROM zbp_industry WHERE geo_id='78613' AND naics_code='541940'")
        assert cur.fetchone() == (7,)
        cur.execute("SELECT count(*) FROM zbp_industry WHERE geo_id='10001'")
        assert cur.fetchone() == (0,)


def test_zbp_refuses_when_geo_area_has_no_zctas_yet(conn):
    """A-C6: `zbp` cannot bound ZIPs to the market states without A4's TIGER load having run
    first -- an empty `geo_area` is a refusal naming the prerequisite, not a network call."""
    def factory(ds):
        raise AssertionError("a missing-boundaries refusal must never build a client")

    with pytest.raises(zbp.MissingBoundaries, match=r"census_load\.py tiger"):
        zbp.load(conn, factory, ["48"])


def test_zbp_upsert_is_idempotent_on_a_rerun(conn):
    _seed_zctas(conn, "78613")

    def handler(r):
        code = r.url.params["NAICS2017"]
        return httpx.Response(200, json=[["ZIPCODE", "ESTAB", "NAICS2017"], ["78613", "7", code]])

    f = factory_for(handler)
    first = zbp.load(conn, f, ["48"])
    second = zbp.load(conn, f, ["48"])
    assert first == second == 4  # one ZIP x 3 NAICS codes + the all-industry total, not doubled
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM zbp_industry")
        assert cur.fetchone() == (4,)


def test_zbp_refuses_a_dataset_that_is_not_cleared(conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'blocked' WHERE dataset_key = 'zbp'")

    def factory(ds):
        raise AssertionError("a blocked dataset must never build a client")

    with pytest.raises(PermissionError):
        zbp.load(conn, factory, ["48"])


def test_qwi_loads_a_quarter_and_trims_to_twenty(conn):
    def handler(r):
        y, q = r.url.params["year"], r.url.params["quarter"]
        return httpx.Response(200, json=[["EarnBeg", "Emp", "HirA", "state", "county", "year", "quarter", "industry"],
                                         ["6120", "4200", "310", "48", "453", y, q, "5419"]])
    f = factory_for(handler)
    for i in range(22):  # 22 quarters back from 2024Q4
        y, q = divmod((2024 * 4 + 3) - i, 4)
        qwi.load(conn, f, ["48"], year=y, quarter=q + 1)
    qwi.trim(conn, keep=20)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), min(year*10+quarter), max(year*10+quarter) FROM qwi_measure WHERE geo_id='48453'")
        n, lo, hi = cur.fetchone()
    assert n == 20 and hi == 20244 and lo == 20201


def test_qwi_county_geo_id_raises_when_the_row_lacks_state_or_county():
    with pytest.raises(ValueError):
        qwi._county_geo_id({"county": "453"})


def test_qwi_refuses_a_dataset_that_is_not_cleared(conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'blocked' WHERE dataset_key = 'qwi'")

    def factory(ds):
        raise AssertionError("a blocked dataset must never build a client")

    with pytest.raises(PermissionError):
        qwi.load(conn, factory, ["48"], year=2024, quarter=4)


def test_qwi_latest_available_walks_back_from_404s():
    def handler(r):
        y, q = int(r.url.params["year"]), int(r.url.params["quarter"])
        return httpx.Response(200, json=[["Emp", "state"], ["1", "48"]]) if (y, q) <= (2024, 4) else httpx.Response(404)
    from app.census.registry import Dataset
    ds = Dataset("qwi", "QWI", "timeseries/qwi/sa", "https://api.census.gov/data", "latest quarter", None, "Quarterly", "cleared", "Public domain", None, "x", None, None)
    client = CensusClient("K", ds, None, transport=httpx.MockTransport(handler), contact=CONTACT)
    assert qwi.latest_available(client, "48", today=(2026, 3)) == (2024, 4)


def test_qwi_latest_available_walks_back_from_the_204s_the_census_actually_sends():
    """Task CENSUS-204, defect 1. Measured on the live API (`task-qwi-bds-runs-report.md` §3):
    an unpublished QWI quarter is **204 with a zero-byte body**, never 404/400 -- and
    `latest_available` seeds its walk at TODAY's quarter while QWI publishes about three quarters
    in arrears, so the very FIRST probe is always one of those. The walk must cross them."""
    from app.census.registry import Dataset

    def handler(r):
        y, q = int(r.url.params["year"]), int(r.url.params["quarter"])
        if (y, q) <= (2025, 4):
            return httpx.Response(200, json=[["Emp", "state"], ["1", "48"]])
        return httpx.Response(204)   # the live shape: 2xx, no body at all

    ds = Dataset("qwi", "QWI", "timeseries/qwi/sa", "https://api.census.gov/data", "latest quarter", None, "Quarterly", "cleared", "Public domain", None, "x", None, None)
    client = CensusClient("K", ds, None, transport=httpx.MockTransport(handler), contact=CONTACT)
    assert qwi.latest_available(client, "48", today=(2026, 3)) == (2025, 4)


def test_qwi_latest_available_gives_up_after_twelve_quarters_of_204s():
    """The bound still holds when every quarter answers the live "no data" shape rather than a
    404 -- a state absent from QWI entirely (Alaska, Michigan) must not loop for ever."""
    from app.census.registry import Dataset

    ds = Dataset("qwi", "QWI", "timeseries/qwi/sa", "https://api.census.gov/data", "latest quarter", None, "Quarterly", "cleared", "Public domain", None, "x", None, None)
    client = CensusClient("K", ds, None, transport=httpx.MockTransport(lambda r: httpx.Response(204)), contact=CONTACT)
    with pytest.raises(RuntimeError, match="no QWI quarter available"):
        qwi.latest_available(client, "02", today=(2026, 3))


def test_qwi_latest_available_reraises_a_non_404_400_error():
    """A status other than 404/400 (e.g. a real outage) is not "this quarter doesn't exist yet"
    -- it must propagate, not be swallowed into an endless walk backwards."""
    from app.census.client import CensusHTTPError
    from app.census.registry import Dataset

    def handler(r):
        return httpx.Response(403)  # not 5xx/429, so CensusClient never retries this one

    ds = Dataset("qwi", "QWI", "timeseries/qwi/sa", "https://api.census.gov/data", "latest quarter", None, "Quarterly", "cleared", "Public domain", None, "x", None, None)
    client = CensusClient("K", ds, None, transport=httpx.MockTransport(handler), contact=CONTACT)

    with pytest.raises(CensusHTTPError) as exc:
        qwi.latest_available(client, "48", today=(2026, 3))
    assert exc.value.status == 403


def test_qwi_latest_available_gives_up_after_twelve_quarters():
    from app.census.registry import Dataset

    def handler(r):
        return httpx.Response(404)  # every quarter probed comes back "doesn't exist"

    ds = Dataset("qwi", "QWI", "timeseries/qwi/sa", "https://api.census.gov/data", "latest quarter", None, "Quarterly", "cleared", "Public domain", None, "x", None, None)
    client = CensusClient("K", ds, None, transport=httpx.MockTransport(handler), contact=CONTACT)

    with pytest.raises(RuntimeError, match="no QWI quarter available"):
        qwi.latest_available(client, "48", today=(2026, 3))


def test_bds_state_rows(conn):
    def handler(r):
        # A-C6: the timeseries/bds variable is `ESTABS_ENTRY`, not `ESTAB_ENTRY`.
        return httpx.Response(200, json=[["FIRM", "ESTABS_ENTRY", "state", "YEAR", "NAICS"], ["18300", "2100", "48", "2022", "54"]])
    assert bds.load(conn, factory_for(handler), ["48"], year=2022) == 1
    with conn.cursor() as cur:
        cur.execute("SELECT geo_id, summary_level, vintage, naics_code, firms, estab_entry FROM bds_measure")
        assert cur.fetchone() == ("48", "040", "2022", "54", 18300, 2100)


def test_bds_refuses_a_dataset_that_is_not_cleared(conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE dataset_registry SET license_status = 'blocked' WHERE dataset_key = 'bds'")

    def factory(ds):
        raise AssertionError("a blocked dataset must never build a client")

    with pytest.raises(PermissionError):
        bds.load(conn, factory, ["48"], year=2022)


# --- one absent state must not fail a whole run (Task CENSUS-204, defect 3) --------------------
# Measured on the live API on 2026-09-14 (`task-qwi-bds-runs-report.md` §3, root cause B): Alaska
# (02) and Michigan (26) are absent from the QWI programme entirely -- 204 with a zero-byte body
# at every quarter back to 2022Q4, with no industry filter at all, so this is not small-cell
# suppression and waiting never fixes it. `SELECT state_fips FROM market_state ORDER BY 1` puts
# Alaska SECOND, so the run used to write Alabama and then die. Nothing here hard-codes those two
# states: the rule is "this state returned no data for this request", measured per run.

def test_qwi_skips_a_state_with_no_data_and_loads_the_rest(conn):
    asked = []

    def handler(r):
        st = r.url.params["in"].split(":")[1]
        asked.append(st)
        if st in ("02", "26"):
            return httpx.Response(204)   # absent from the programme, not late
        return httpx.Response(200, json=[["EarnBeg", "Emp", "HirA", "state", "county", "year", "quarter", "industry"],
                                         [f"{6000 + int(st)}", "4200", "310", st, "453", "2025", "4", "5419"]])

    written = qwi.load(conn, factory_for(handler), ["01", "02", "26", "48"], year=2025, quarter=4)
    assert written == 2                       # the two states that publish
    assert asked == ["01", "02", "26", "48"]  # every state was still tried, in order
    with conn.cursor() as cur:
        cur.execute("SELECT geo_id FROM qwi_measure ORDER BY geo_id")
        assert [r[0] for r in cur.fetchall()] == ["01453", "48453"]
        cur.execute("SELECT status, rows_written, notes FROM ingest_run WHERE dataset_key='qwi' ORDER BY id DESC LIMIT 1")
        status, rows, notes = cur.fetchone()
    assert status == "succeeded" and rows == 2
    # The run row says WHICH states were skipped and WHY -- the ledger is the only durable record
    # a scheduled run leaves behind.
    assert notes == "qwi: no data for state 02 at 2025Q4; skipped\nqwi: no data for state 26 at 2025Q4; skipped"


def test_qwi_records_no_notes_when_every_state_publishes(conn):
    def handler(r):
        st = r.url.params["in"].split(":")[1]
        return httpx.Response(200, json=[["EarnBeg", "Emp", "HirA", "state", "county", "year", "quarter", "industry"],
                                         ["6120", "4200", "310", st, "453", "2025", "4", "5419"]])

    qwi.load(conn, factory_for(handler), ["01", "48"], year=2025, quarter=4)
    with conn.cursor() as cur:
        cur.execute("SELECT notes FROM ingest_run WHERE dataset_key='qwi' ORDER BY id DESC LIMIT 1")
        assert cur.fetchone()[0] is None


def test_bds_skips_a_state_with_no_data_and_records_it(conn):
    """Not QWI-specific: the report measured BDS **2024** answering with no body at all while
    2021-2023 serve cleanly, so the same absence can arrive one year or one state at a time."""
    def handler(r):
        st = r.url.params["for"].split(":")[1]
        if st == "02":
            return httpx.Response(204)
        return httpx.Response(200, json=[["FIRM", "ESTABS_ENTRY", "state", "YEAR", "NAICS"], ["18300", "2100", st, "2023", "54"]])

    assert bds.load(conn, factory_for(handler), ["02", "48"], year=2023) == 1
    with conn.cursor() as cur:
        cur.execute("SELECT geo_id FROM bds_measure")
        assert [r[0] for r in cur.fetchall()] == ["48"]
        cur.execute("SELECT status, notes FROM ingest_run WHERE dataset_key='bds' ORDER BY id DESC LIMIT 1")
        assert cur.fetchone() == ("succeeded", "bds: no data for state 02 in 2023; skipped")


def test_cbp_skips_a_state_and_naics_code_with_no_data_and_records_it(conn):
    def handler(r):
        st, code = r.url.params["in"].split(":")[1], r.url.params["NAICS2017"]
        if st == "02":
            return httpx.Response(204)
        return httpx.Response(200, json=[["NAME", "ESTAB", "EMP", "PAYANN", "EMP_N", "PAYANN_N", "state", "county", "NAICS2017"],
                                         ["Travis County, Texas", "12", "410", "38500", None, None, st, "453", code]])

    assert cbp.load(conn, factory_for(handler), ["02", "48"]) == 3   # one county x three NAICS codes
    with conn.cursor() as cur:
        cur.execute("SELECT status, notes FROM ingest_run WHERE dataset_key='cbp' ORDER BY id DESC LIMIT 1")
        status, notes = cur.fetchone()
    assert status == "succeeded"
    assert notes.splitlines() == ["cbp: no data for state 02, NAICS 541940; skipped",   # cbp.NAICS order
                                  "cbp: no data for state 02, NAICS 812910; skipped",
                                  "cbp: no data for state 02, NAICS 459910; skipped"]


def test_zbp_skips_a_naics_code_with_no_data_and_records_it(conn):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO geo_area (geo_id, summary_level, vintage, name, geom) VALUES ('78704','860','2023','ZCTA5 78704', ST_Multi(ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 1,0 0))',4269)))")

    def handler(r):
        code = r.url.params["NAICS2017"]
        if code == "541940":
            return httpx.Response(204)
        return httpx.Response(200, json=[["ESTAB", "ZIPCODE", "NAICS2017"], ["7", "78704", code]])

    assert zbp.load(conn, factory_for(handler), ["48"]) == 3   # four codes requested, one absent
    with conn.cursor() as cur:
        cur.execute("SELECT status, notes FROM ingest_run WHERE dataset_key='zbp' ORDER BY id DESC LIMIT 1")
        assert cur.fetchone() == ("succeeded", "zbp: no data for NAICS 541940; skipped")
