"""Census Geocoder client, address cache and §11 fallback ladder (Task B2; spec §2 geocoder,
§6 resolution order, §10 365-day cache, §11 fallbacks -- "flag for staff" below rooftop).

Resolution order: an address is normalised and hashed; a live cache row (`geocode_cache`,
`expires_at > now()`) is served without a second HTTP call, whether it holds a real match OR a
recorded "no geocoder match" -- both are cached (§10), a nomatch included, so a bad address is
not re-queried every time a listing is touched. A cache miss calls the Census Geocoder itself
(`Geocoder.lookup`); a real match resolves at "rooftop" precision when its geographies carry a
Census Tract (almost always, once `layers=all` is requested -- see below), else "tract". No
match at all runs the fallback ladder: the ZCTA containing the listing's ZIP code, centroid of
its CONTAINING tract (`tract`/`county_geoid` inherited from that tract, not the ZCTA itself);
else the state's own place boundary whose name starts with the listing's city; else
`GeocodeFailed` -- SP2 (not built in this phase) reads that exception's own message into the
seller's draft status, so it is never caught here, only by `app.tasks.census.geocode_listing`'s
narrower `_NotReady` gate for a missing contact.

Every resolution -- ladder rung or fallback -- writes `practice_location` (upserted on
`listing_id`), and `geocode_review` gets a row whenever the precision lands below "rooftop" (the
market panel's "approximate community data" notice, per §11).

Controller amendment A-C15 corrections, applied here (not rediscovered):
  2 -- `STATE_FIPS` is an explicit six-entry mapping (the states `market_state`/migration 017
       pins: California, Texas, Florida, Georgia, New York, Colorado) to their two-digit FIPS
       codes, and `_fallback`'s place query filters `geo_area.state_fips` directly against it.
       The brief's own illustrative code instead joined through a `geo_area` name lookup on
       `summary_level = '040'` state rows, gated by a FOUR-entry name map -- which would refuse
       New York and Colorado (Denver) outright even before considering whether TIGER's own state
       boundary rows carry a name a joined predicate could ever match. `tests/census/
       test_geocode.py::test_state_fips_matches_the_market_state_registry` pins the six entries
       against the registry so the two can never drift apart silently.
  3 -- `layers=all` is on every geocoder request (`Geocoder.lookup`'s own `params`): without it
       the service returns no ZIP-code-area and no metropolitan-area geography at all, so
       `zcta_geoid`/`cbsa_geoid` would be empty for every listing regardless of precision.
  4 -- `tests/census/fixtures/geocoder_match.json` and `geocoder_nomatch.json` are REAL recorded
       responses (a keyless GET, read-only, no ingestion -- captured 2026-09-09 against
       `450 Cypress Creek Rd, Cedar Park, TX 78613`, Cedar Park City Hall, and a nonsense
       address), not the brief's own invented shape -- see `test_geocode.py`'s module docstring
       for the full provenance note.

`_first_geoid` reads the FIRST geography row under any key containing one of its needles --
`layers=all` returns dozens of geography layers per match (congressional districts, school
districts, urban areas, …) that this module has no use for, so it looks for the ones it wants by
substring rather than an exhaustive key list, which is also what lets "2020 Census ZIP Code
Tabulation Areas" (the real key) satisfy a "ZIP Code Tabulation Areas" needle."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import cast

import httpx
import psycopg2.extensions

#: A-C15 correction 2: the six states `market_state` (migration 017) pins, mapped to their
#: two-digit FIPS codes -- `_fallback`'s place query filters `geo_area.state_fips` against this
#: directly. `tests/census/test_geocode.py::test_state_fips_matches_the_market_state_registry`
#: is the drift test correction 2 asks for.
STATE_FIPS = {
    "CA": "06",
    "TX": "48",
    "FL": "12",
    "GA": "13",
    "NY": "36",
    "CO": "08",
}

#: The Census Geocoder benchmark/vintage pair every request in this module pins (spec §6) --
#: distinct from the TIGER cartographic `vintage` `_tiger_vintage`/`_fallback` read out of
#: `active_vintage`, which is a boundary-file release year, not a geocoder benchmark.
GEOCODER_VINTAGE = "Current_Current"


class GeocodeFailed(Exception):
    """Nothing resolved -- not even a fallback. The listing stays in draft; SP2 reads this
    exception's own message into the seller's draft status, so its text is written to matter."""


@dataclass(frozen=True)
class Match:
    lat: float
    lng: float
    matched_address: str
    tract_geoid: str | None
    county_geoid: str | None
    place_geoid: str | None
    zcta_geoid: str | None
    cbsa_geoid: str | None


@dataclass(frozen=True)
class Location:
    listing_id: str
    geo_precision: str
    lat: float | None
    lng: float | None
    tract_geoid: str | None
    county_geoid: str | None
    place_geoid: str | None
    zcta_geoid: str | None
    cbsa_geoid: str | None


def normalize(street: str, city: str, state: str, zip_: str) -> str:
    """Case/punctuation-insensitive, so "1 Main St." and "1  MAIN ST" hash identically; the ZIP
    is truncated to five digits so a ZIP+4 does not split one address's cache row in two."""

    def clean(s: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", (s or "").lower())).strip()

    return "|".join([clean(street), clean(city), clean(state), (zip_ or "").strip()[:5]])


def address_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode()).hexdigest()


def _first_geoid(geographies: dict[str, list[dict[str, str]]], *needles: str) -> str | None:
    """The first GEOID under any geography key containing one of `needles` as a substring, or
    `None` when no such key has any rows -- a key can be present with an empty list (a real
    geography layer simply absent for this address), which must be skipped rather than treated
    as a match."""
    for key, rows in geographies.items():
        if rows and any(needle in key for needle in needles):
            return rows[0].get("GEOID")
    return None


class Geocoder:
    def __init__(self, http: httpx.Client, base_url: str, user_agent: str) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.ua = user_agent

    def lookup(self, street: str, city: str, state: str, zip_: str) -> Match | None:
        params = {
            "street": street,
            "city": city,
            "state": state,
            "zip": zip_,
            "benchmark": "Public_AR_Current",
            "vintage": GEOCODER_VINTAGE,
            # A-C15 correction 3: without this, the service returns no ZIP-code-area and no
            # metropolitan-area geography for any match.
            "layers": "all",
            "format": "json",
        }
        resp = self.http.get(
            f"{self.base_url}/geographies/address",
            params=params,
            headers={"User-Agent": self.ua},
            timeout=httpx.Timeout(connect=15.0, read=45.0, write=15.0, pool=15.0),
        )
        resp.raise_for_status()
        matches = resp.json().get("result", {}).get("addressMatches", [])
        if not matches:
            return None
        m = matches[0]
        g = m.get("geographies", {})
        return Match(
            lat=float(m["coordinates"]["y"]),
            lng=float(m["coordinates"]["x"]),
            matched_address=m.get("matchedAddress", ""),
            tract_geoid=_first_geoid(g, "Census Tracts"),
            county_geoid=_first_geoid(g, "Counties"),
            place_geoid=_first_geoid(g, "Incorporated Places", "Census Designated Places"),
            zcta_geoid=_first_geoid(g, "ZIP Code Tabulation Areas"),
            cbsa_geoid=_first_geoid(g, "Metropolitan Statistical Areas"),
        )


def _match_payload(m: Match) -> dict[str, object]:
    return {
        "lat": m.lat,
        "lng": m.lng,
        "matched_address": m.matched_address,
        "tract_geoid": m.tract_geoid,
        "county_geoid": m.county_geoid,
        "place_geoid": m.place_geoid,
        "zcta_geoid": m.zcta_geoid,
        "cbsa_geoid": m.cbsa_geoid,
    }


def _cache_lookup(conn: psycopg2.extensions.connection, h: str) -> tuple[bool, Match | None]:
    """`(cache hit, Match | None)`. A hit with `Match` `None` is a cached "no geocoder match"
    (§10): the geocoder itself must not be re-queried for it within the 365-day window, but the
    caller still runs the §11 fallback ladder for it."""
    with conn.cursor() as cur:
        cur.execute("SELECT payload FROM geocode_cache WHERE address_hash = %s AND expires_at > now()", (h,))
        row = cur.fetchone()
    if row is None:
        return False, None
    payload = row[0]
    if payload.get("nomatch"):
        return True, None
    return True, Match(**payload)


def _cache_write(conn: psycopg2.extensions.connection, h: str, normalized: str, m: Match | None) -> None:
    payload: dict[str, object] = {"nomatch": True} if m is None else _match_payload(m)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO geocode_cache (address_hash, normalized_address, payload) VALUES (%s, %s, %s)
               ON CONFLICT (address_hash) DO UPDATE
                 SET payload = EXCLUDED.payload, geocoded_at = now(), expires_at = now() + interval '365 days'""",
            (h, normalized, json.dumps(payload)),
        )


def _tiger_vintage(conn: psycopg2.extensions.connection) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT vintage FROM active_vintage WHERE dataset_key = 'tiger_cb'")
        row = cur.fetchone()
    if row is None:
        raise GeocodeFailed("no active tiger_cb vintage -- run census_load.py tiger and activate it")
    return str(row[0])


def _flt(v: object) -> float | None:
    return float(v) if isinstance(v, int | float) else None


def _txt(v: object) -> str | None:
    return v if isinstance(v, str) else None


def _fallback(conn: psycopg2.extensions.connection, city: str, state_abbr: str, zip_: str, vintage: str) -> tuple[str, dict[str, object]]:
    """§11: ZCTA centroid, inheriting the tract/county it falls inside -> else the state's own
    place boundary whose name starts with the city -> else `GeocodeFailed`.

    A-C15 correction 2: the place query filters `geo_area.state_fips` directly against
    `STATE_FIPS`, never by joining to a `geo_area` row's own name -- a listing whose state is
    not one of the six ruled ones (`state_fips is None`) skips the place query entirely rather
    than running a query that can only ever return nothing."""
    state_fips = STATE_FIPS.get(state_abbr.upper())
    with conn.cursor() as cur:
        cur.execute(
            """SELECT z.geo_id, ST_X(z.centroid), ST_Y(z.centroid), t.geo_id, t.parent_geo_id
               FROM geo_area z
               LEFT JOIN geo_area t ON t.summary_level = '140' AND t.vintage = z.vintage AND ST_Contains(t.geom, z.centroid)
               WHERE z.summary_level = '860' AND z.vintage = %s AND z.geo_id = %s""",
            (vintage, (zip_ or "")[:5]),
        )
        zrow = cur.fetchone()
        if zrow and zrow[3]:
            return "zcta", {"zcta_geoid": zrow[0], "lng": zrow[1], "lat": zrow[2], "tract_geoid": zrow[3], "county_geoid": zrow[4]}
        if state_fips is not None:
            cur.execute(
                """SELECT geo_id, ST_X(centroid), ST_Y(centroid) FROM geo_area
                   WHERE summary_level = '160' AND vintage = %s AND state_fips = %s AND lower(name) LIKE lower(%s) || ' %%'
                   LIMIT 1""",
                (vintage, state_fips, city),
            )
            prow = cur.fetchone()
            if prow:
                return "place", {"place_geoid": prow[0], "lng": prow[1], "lat": prow[2]}
    raise GeocodeFailed(f"no geocoder match and no ZCTA/place fallback for {city!r} {zip_!r} in state {state_abbr!r}")


def resolve(conn: psycopg2.extensions.connection, geocoder: Geocoder, listing_id: str) -> Location:
    with conn.cursor() as cur:
        cur.execute("SELECT street, city, state, zip FROM listing WHERE id = %s", (listing_id,))
        # `resolve` is only ever called with a real listing's id (the caller -- geocode_listing,
        # SP2 later -- creates the row first), so a missing row here is not a modelled failure
        # mode; the cast documents that assumption instead of adding an untested defensive branch.
        street, city, state, zip_ = cast("tuple[str, str, str, str]", cur.fetchone())
    normalized = normalize(street, city, state, zip_)
    h = address_hash(normalized)
    vintage = _tiger_vintage(conn)

    hit, m = _cache_lookup(conn, h)
    if not hit:
        m = geocoder.lookup(street, city, state, zip_)
        _cache_write(conn, h, normalized, m)

    fields: dict[str, object]
    if m is not None:
        precision = "rooftop" if m.tract_geoid else "tract"
        fields = _match_payload(m)
    else:
        precision, fields = _fallback(conn, city, state, zip_, vintage)

    loc = Location(
        listing_id,
        precision,
        _flt(fields.get("lat")),
        _flt(fields.get("lng")),
        _txt(fields.get("tract_geoid")),
        _txt(fields.get("county_geoid")),
        _txt(fields.get("place_geoid")),
        _txt(fields.get("zcta_geoid")),
        _txt(fields.get("cbsa_geoid")),
    )
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO practice_location
                 (listing_id, address_hash, point, tract_geoid, county_geoid, place_geoid, zcta_geoid, cbsa_geoid,
                  geo_precision, geocoded_at, geocoder_vintage)
               VALUES (%s, %s,
                       CASE WHEN %s IS NULL THEN NULL ELSE ST_SetSRID(ST_MakePoint(%s, %s), 4269) END,
                       %s, %s, %s, %s, %s, %s, now(), %s)
               ON CONFLICT (listing_id) DO UPDATE SET
                 address_hash = EXCLUDED.address_hash, point = EXCLUDED.point,
                 tract_geoid = EXCLUDED.tract_geoid, county_geoid = EXCLUDED.county_geoid,
                 place_geoid = EXCLUDED.place_geoid, zcta_geoid = EXCLUDED.zcta_geoid,
                 cbsa_geoid = EXCLUDED.cbsa_geoid, geo_precision = EXCLUDED.geo_precision,
                 geocoded_at = now(), geocoder_vintage = EXCLUDED.geocoder_vintage""",
            (
                listing_id,
                h,
                loc.lng,
                loc.lng,
                loc.lat,
                loc.tract_geoid,
                loc.county_geoid,
                loc.place_geoid,
                loc.zcta_geoid,
                loc.cbsa_geoid,
                precision,
                GEOCODER_VINTAGE,
            ),
        )
        if precision != "rooftop":
            cur.execute(
                "INSERT INTO geocode_review (listing_id, reason) VALUES (%s, %s)",
                (listing_id, f"geocoder fell back to {precision}; market panel shows 'approximate community data'"),
            )
    return loc
