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
    assert zbp.load(conn, factory_for(handler), ["48"]) == 6  # 2 in-bounds ZIPs x 3 NAICS codes
    assert len(urls) == 3
    assert all("for=zip%20code:*" in u and "in=" not in u for u in urls)
    assert any("NAICS2017=453910" in u for u in urls) and not any("459910" in u for u in urls)
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
    assert first == second == 3  # one ZIP x 3 NAICS codes, not doubled by the re-run
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM zbp_industry")
        assert cur.fetchone() == (3,)


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
