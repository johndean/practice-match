"""D2: "A test asserts every point lies inside its state's bounding box and within 25 km of
its city's centroid." The tables below are committed here so the test is self-contained and
never touches the network — the geocoder runs once, by hand, and its output is the data.

STATE_BBOX is the conventional bounding box of each state's land area (south, west, north,
east) in WGS-84 degrees. CITY_CENTROID is each city's civic centre. Both are reference data,
not measurements of the seeds: a seed that falls outside is a bad geocode, and the fix is to
re-geocode or to STOP and ask John — never to widen a bound (Global Constraint (l)).

Measured margin, for the implementer's information: the Dallas seed (17727 Dallas Pkwy, far
North Dallas) sits ~24.1 km from the Dallas centroid — the tightest of the eighteen against
the 25 km limit. If it fails, the coordinate is wrong, not the limit.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SEEDS = ROOT / "seeds" / "hospitals.json"
MAX_KM_FROM_CITY = 25.0
EARTH_RADIUS_KM = 6371.0088

# state: (south_lat, west_lng, north_lat, east_lng)
STATE_BBOX: dict[str, tuple[float, float, float, float]] = {
    "TX": (25.837, -106.646, 36.501, -93.508),
    "NY": (40.496, -79.763, 45.016, -71.856),
    "CO": (36.993, -109.061, 41.003, -102.041),
    "CA": (32.529, -124.482, 42.010, -114.131),
    "FL": (24.396, -87.635, 31.001, -79.974),
    "GA": (30.356, -85.605, 35.001, -80.840),
}

CITY_CENTROID: dict[str, tuple[float, float]] = {
    "Dallas, TX": (32.7767, -96.7970),
    "New York, NY": (40.7128, -74.0060),
    "Denver, CO": (39.7392, -104.9903),
    "Santa Barbara, CA": (34.4208, -119.6982),
    "Houston, TX": (29.7604, -95.3698),
    "Los Angeles, CA": (34.0522, -118.2437),
    "South Lake Tahoe, CA": (38.9332, -119.9843),
    "Sacramento, CA": (38.5816, -121.4944),
    "Orlando, FL": (28.5383, -81.3792),
    "Atlanta, GA": (33.7490, -84.3880),
    "Austin, TX": (30.2672, -97.7431),
}


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def hospitals() -> list[dict[str, object]]:
    return json.loads(SEEDS.read_text(encoding="utf-8"))["hospitals"]


def test_every_city_in_the_seed_file_has_a_committed_centroid() -> None:
    missing = {str(h["market"]) for h in hospitals()} - set(CITY_CENTROID)
    assert missing == set(), f"add a centroid for {sorted(missing)} — do not skip the check"


def test_every_state_in_the_seed_file_has_a_committed_bbox() -> None:
    missing = {str(h["state"]) for h in hospitals()} - set(STATE_BBOX)
    assert missing == set(), f"add a bounding box for {sorted(missing)} — do not skip the check"


def test_every_point_is_inside_its_states_bounding_box() -> None:
    for h in hospitals():
        south, west, north, east = STATE_BBOX[str(h["state"])]
        lat, lng = float(h["lat"]), float(h["lng"])
        assert south <= lat <= north, (h["slug"], "lat", lat, (south, north))
        assert west <= lng <= east, (h["slug"], "lng", lng, (west, east))


def test_every_point_is_within_25_km_of_its_city_centroid() -> None:
    for h in hospitals():
        km = haversine_km((float(h["lat"]), float(h["lng"])), CITY_CENTROID[str(h["market"])])
        assert km <= MAX_KM_FROM_CITY, (h["slug"], round(km, 2))


# The one coordinate verified live against the Census Geocoder (2026-09-06). `Public_AR_Current`
# is a ROLLING benchmark, so a later run can legitimately return a slightly different point.
# RECOURSE (pre-flight I9): a differing coordinate that still passes the bounding-box and 25 km
# tests above is acceptable — update this constant in the same commit and record the change in
# the hand-back note. A coordinate that fails either bound is a STOP for John. Do not delete
# this test to make a re-geocode pass; the bounds are the spec's requirement, this is the audit
# trail. Measured headroom on the committed value: 24.09 km against the 25 km limit (0.91 km).
DALLAS_ANCHOR = (32.991596, -96.829738)


def test_the_dallas_anchor_is_the_probed_coordinate() -> None:
    dallas = next(h for h in hospitals() if h["slug"] == "6666_dallas_veterinary_specialist_hospital")
    assert (dallas["lat"], dallas["lng"]) == DALLAS_ANCHOR


def test_no_two_hospitals_share_a_coordinate() -> None:
    points = [(h["lat"], h["lng"]) for h in hospitals()]
    assert len(set(points)) == len(points), "two seeds geocoded to the same point — check the run"
