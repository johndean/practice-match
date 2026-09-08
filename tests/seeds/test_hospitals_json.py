"""seeds/hospitals.json is John's table of 2026-09-06, verbatim (spec §2), plus the fields
the design needs that his table does not carry (D4) and the coordinates the implementer
geocoded once (D2). This file is the contract every later task reads."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SEEDS = ROOT / "seeds" / "hospitals.json"
PHOTO_SOURCE_SUFFIX = "_individual_images"

# John's table, verbatim: (name, city, state, street, zip, phone, hours). The EN DASH in his
# opening hours is written `\u2013` — the same escape convention tests/api/test_auth.py uses —
# so ruff's RUF001 (ambiguous unicode) has nothing to flag and no ignore is added; the string
# values are byte-identical to the spec's.
JOHNS_TABLE: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    ("6666 Dallas Veterinary Specialist Hospital", "Dallas", "TX", "17727 Dallas Pkwy, Suite 150", "75287", "(214) 555-0101", "Mon\u2013Fri 8 AM\u20135 PM"),
    ("5555 New York Veterinary Specialist Hospital", "New York", "NY", "510 E 62nd St", "10065", "(212) 555-0102", "24/7"),
    ("4444 Denver Veterinary Specialist Hospital", "Denver", "CO", "9770 E Alameda Ave", "80247", "(303) 555-0103", "24/7"),
    ("3333 Santa Barbara Veterinary Specialist Hospital", "Santa Barbara", "CA", "414 E Carrillo St", "93101", "(805) 555-0104", "24/7"),
    ("2222 Pet Hospital", "Houston", "TX", "8042 Katy Freeway", "77024", "(713) 555-0105", "24/7 emergency"),
    ("1111 Pet Hospital", "Los Angeles", "CA", "6565 Santa Monica Blvd", "90038", "(323) 555-0106", "24/7"),
    ("789 Lake Tahoe Pet Hospital", "South Lake Tahoe", "CA", "921 Emerald Bay Rd", "96150", "(530) 555-0107", "Mon\u2013Sat 8 AM\u20136 PM"),
    ("456 Pet ER Hospital", "Los Angeles", "CA", "2500 N San Fernando Rd", "90065", "(323) 555-0108", "24/7"),
    ("123 Route 66 Animal Hospital", "Los Angeles", "CA", "4641 Colorado Blvd", "90039", "(818) 555-0109", "24/7"),
    ("YZ Rural Animal Hospital", "Sacramento", "CA", "8299 E Stockton Blvd", "95828", "(916) 555-0110", "24/7"),
    ("VWX Veterinary Hospital", "Orlando", "FL", "11011 Lake Underhill Rd", "32825", "(407) 555-0111", "24/7"),
    ("STU Veterinary Specialist Center", "Orlando", "FL", "2080 Principal Row", "32837", "(407) 555-0112", "Mon\u2013Thu 8 AM\u20136 PM"),
    ("PQR Veterinary Hospital", "Sacramento", "CA", "9801 Old Winery Place", "95827", "(916) 555-0113", "6 AM\u201312 AM"),
    ("MNO Pet Hospital", "Sacramento", "CA", "1917 P Street", "95811", "(916) 555-0114", "Mon\u2013Fri 8 AM\u20136 PM; Sat 9 AM\u20135 PM"),
    ("JKL Animal Critical Care & ER Hospital", "Atlanta", "GA", "1700 Century Cir NE", "30345", "(404) 555-0115", "24/7"),
    ("GHI Veterinary Hospital", "Austin", "TX", "7501 N Capital of Texas Hwy, Building A", "78731", "(512) 555-0116", "24/7 emergency"),
    ("DEF Veterinary Hospital", "Austin", "TX", "4434 Frontier Trail", "78745", "(512) 555-0117", "24/7"),
    ("ABC Animal Hospital", "Houston", "TX", "6730 Airline Dr", "77076", "(713) 555-0118", "Mon/Tue/Thu/Fri 7:30 AM\u20136 PM; Sat 7:30 AM\u20135 PM"),
)

REQUIRED_KEYS = {
    "slug", "name", "street", "city", "state", "zip", "phone", "hours", "area", "market", "type",
    "status", "source", "location_disclosed", "name_disclosed", "lat", "lng", "geocode", "demo",
    "price", "rev", "docs", "rooms", "sqft", "bldg", "est", "listed_days_ago",
    "note", "staff", "services", "facility", "ownership",
}


def load() -> list[dict[str, object]]:
    data = json.loads(SEEDS.read_text(encoding="utf-8"))
    assert data["version"] == 1
    hospitals = data["hospitals"]
    assert isinstance(hospitals, list)
    return hospitals


def derived_type(name: str, hours: str) -> str:
    """D4, in the order D4 states it: Specialist wins over emergency hours."""
    if "Specialist" in name:
        return "Specialty"
    if "ER" in name.split() or "Critical Care" in name or "24/7 emergency" in hours:
        return "Emergency"
    return "Small animal"


def test_there_are_exactly_eighteen_hospitals() -> None:
    assert len(load()) == 18


def test_johns_table_is_reproduced_verbatim_and_in_order() -> None:
    rows = load()
    got = tuple((h["name"], h["city"], h["state"], h["street"], h["zip"], h["phone"], h["hours"]) for h in rows)
    assert got == JOHNS_TABLE


def test_every_hospital_carries_every_contracted_key() -> None:
    for h in load():
        assert set(h) == REQUIRED_KEYS, (h["slug"], set(h) ^ REQUIRED_KEYS)


def test_type_is_derived_exactly_as_d4_says() -> None:
    for h in load():
        assert h["type"] == derived_type(str(h["name"]), str(h["hours"])), h["slug"]


def test_the_derivation_produces_five_specialty_four_emergency_and_nine_small_animal() -> None:
    counts: dict[str, int] = {}
    for h in load():
        counts[str(h["type"])] = counts.get(str(h["type"]), 0) + 1
    assert counts == {"Specialty": 5, "Emergency": 4, "Small animal": 9}


def test_every_phone_is_a_555_number() -> None:
    for h in load():
        assert " 555-" in str(h["phone"]), h["slug"]


def test_area_and_market_are_derived_from_the_city_and_state() -> None:
    for h in load():
        assert h["area"] == h["city"], h["slug"]
        assert h["market"] == f"{h['city']}, {h['state']}", h["slug"]


def test_every_row_is_a_published_disclosed_demo_seed() -> None:
    for h in load():
        assert h["status"] == "published" and h["source"] == "seed", h["slug"]
        assert h["location_disclosed"] is True and h["demo"] is True, h["slug"]
        assert h["note"] == "Demo listing seeded by the VIN Foundation.", h["slug"]


def test_every_row_discloses_its_name() -> None:
    """A-L5: `name_disclosed` is per listing, seller-set and admin-overridable, and defaults to
    false in migration 016. John's eighteen demo hospitals show their names on QA, so every seed
    row sets it true explicitly — the key is required here and its type is pinned to bool, so a
    row that omits it or carries a truthy string never reaches the seeder."""
    for h in load():
        assert isinstance(h["name_disclosed"], bool), (h["slug"], type(h["name_disclosed"]).__name__)
        assert h["name_disclosed"] is True, h["slug"]


def test_the_demo_business_fields_are_present_and_plausible() -> None:
    """A-L2.1: the floor was 500,000, which contradicted the design's own "Under $500K" band —
    the plan invented that number, the band is the design's, so the floor gives way. It is
    400,000 here and `abc_animal_hospital` (1 DVM, 2,400 sq ft, est. 1987) is priced at 465,000,
    which is what covers `price`/`u500` in the A-L2 test below."""
    for h in load():
        assert isinstance(h["price"], int) and 400_000 <= int(h["price"]) <= 4_000_000, h["slug"]
        assert isinstance(h["rev"], int) and int(h["rev"]) > int(h["price"]) * 0.5, h["slug"]
        assert 1 <= int(h["docs"]) <= 12 and 1 <= int(h["rooms"]) <= 12, h["slug"]
        assert 2_000 <= int(h["sqft"]) <= 12_000, h["slug"]
        assert h["bldg"] in ("Included", "Leased", "Separate"), h["slug"]
        assert 1900 <= int(h["est"]) <= 2026, h["slug"]
        assert 0 <= int(h["listed_days_ago"]) <= 60, h["slug"]
        for text_field in ("staff", "services", "facility", "ownership"):
            assert isinstance(h[text_field], str) and h[text_field], (h["slug"], text_field)


# The eighteen curated photograph folders are named `<slug>_individual_images`. Pinning the
# set here is what lets scripts/prepare_photos.py map folder -> hospital with no lookup table,
# and what catches a slug being "tidied up" without its folder.
PHOTO_FOLDER_SLUGS = frozenset({
    "6666_dallas_veterinary_specialist_hospital", "5555_new_york_veterinary_specialist_hospital",
    "4444_denver_veterinary_specialist_hospital", "3333_santa_barbara_veterinary_specialist_hospital",
    "2222_pet_hospital", "1111_pet_hospital", "789_lake_tahoe_pet_hospital", "456_pet_er",
    "123_route66", "yz_rural_animal_hospital", "vwx_veterinary_hospital",
    "stu_veterinary_specialist_center", "pqr_veterinary_hospital", "mno_pet_hospital",
    "jkl_animal_hospital", "ghi_veterinary_hospital", "def_veterinary_hospital",
    "abc_animal_hospital",
})
PHOTO_FOLDER_NAMES = frozenset(slug + PHOTO_SOURCE_SUFFIX for slug in PHOTO_FOLDER_SLUGS)


def test_slugs_are_unique_and_name_the_photograph_folders() -> None:
    slugs = [str(h["slug"]) for h in load()]
    assert len(set(slugs)) == 18
    assert set(slugs) == PHOTO_FOLDER_SLUGS
    for slug in slugs:
        assert slug == slug.lower() and " " not in slug, slug
        # The folder scripts/prepare_photos.py will actually open, pinned as a set rather than
        # re-derived — a concatenation of two non-empty strings is always truthy and proves
        # nothing (pre-flight M1).
        assert (slug + PHOTO_SOURCE_SUFFIX) in PHOTO_FOLDER_NAMES, slug


def test_the_geocode_provenance_is_recorded() -> None:
    for h in load():
        geo = h["geocode"]
        assert isinstance(geo, dict)
        assert geo["benchmark"] == "Public_AR_Current", h["slug"]
        assert geo["tier"] in ("exact", "approximate"), (h["slug"], geo["tier"])
        assert isinstance(geo["matched_address"], str) and geo["matched_address"], h["slug"]


def _spec_table_rows() -> list[tuple[str, str, str, str, str]]:
    """§2 of the spec, parsed out of its markdown table: (name, city/state, address, phone, hours).

    Pre-flight I12: `JOHNS_TABLE` above is a hand-typed SECOND copy of John's table, so a typo
    made in both copies passes silently. John's standing rule is a drift test wherever a
    document and code can diverge — this is that test's data source, read from the spec itself."""
    spec = (ROOT / "docs" / "superpowers" / "specs" / "2026-09-06-seed-listings-design.md")
    rows: list[tuple[str, str, str, str, str]] = []
    for line in spec.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith(("| ---", "|---")):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5 or cells[0] in ("Seed hospital", "") or set(cells[0]) <= set("-: "):
            continue
        rows.append((cells[0], cells[1], cells[2], cells[3], cells[4]))
    return rows


def test_the_spec_table_parses_to_exactly_eighteen_rows() -> None:
    assert len(_spec_table_rows()) == 18, "the §2 table parser no longer matches the spec's markdown"


def test_the_seed_file_reconstructs_the_spec_table_exactly() -> None:
    """Every row of §2, rebuilt from seeds/hospitals.json and compared to the spec verbatim."""
    rebuilt = [
        (
            str(h["name"]),
            f"{h['city']}, {h['state']}",
            f"{h['street']}, {h['city']}, {h['state']} {h['zip']}",
            str(h["phone"]),
            str(h["hours"]),
        )
        for h in load()
    ]
    assert rebuilt == _spec_table_rows()


def test_no_geocode_placeholder_survived_the_run() -> None:
    """`tier` is pre-filled and `matched_address` is a non-empty sentinel in the plan's JSON
    body, so membership and non-emptiness alone cannot catch an unreplaced row (pre-flight
    I10). The Census geocoder returns `matchedAddress` upper-cased, and the city has to appear
    in it — the cheap way to catch a match in the wrong town."""
    for h in load():
        matched = str(h["geocode"]["matched_address"])
        assert "REPLACE" not in matched, h["slug"]
        assert matched == matched.upper(), (h["slug"], matched)
        assert str(h["city"]).upper() in matched.upper(), (h["slug"], matched)


def test_community_figures_are_absent_until_the_census_plan_supplies_them() -> None:
    """D4: pop/growth/income/hh are left null; the UI shows its existing empty state."""
    for h in load():
        for field in ("pop", "growth", "income", "hh"):
            assert field not in h, (h["slug"], field)


# --------------------------------------------------------------------------------------
# Controller amendment A-L2 (John: "I have provided the hospital seed data & only need to
# generate fake data for all missing fields to cover all filters in the BROWSE PRACTICES").
#
# The demo values are DISTRIBUTED, not merely plausible: every non-"Any" option of every
# Browse filter matches at least one of the eighteen, and every "Any" matches all eighteen.
# The option lists are READ from the design (frontend/src/logic.js) rather than retyped, so
# a design change is noticed here; "matches" is the design's own predicate, arm for arm.
# --------------------------------------------------------------------------------------

LOGIC_JS = ROOT / "frontend" / "src" / "logic.js"

# A-L2.2 (John, 2026-09-08, asked whether any of the eighteen is a Mixed or a Large-animal
# practice): "they are all Small Animal". None of his hospitals is either, so these two options
# are excluded from the coverage requirement BY NAME and the demo set returns no results for
# them on QA. D4's name-based derivation is unchanged for the rest. The exclusion is pinned in
# both directions below — a hospital that ever DID match one of these would fail
# test_johns_ruling_still_holds_no_hospital_is_mixed_or_large_animal, which is the signal to
# take the question back to John rather than to quietly widen the list.
JOHNS_RULING = "they are all Small Animal"
EXCLUDED_OPTIONS: frozenset[tuple[str, str]] = frozenset({("type", "Mixed"), ("type", "Large animal")})

# The design's two filter blocks, pinned. `filters:` is the bar (five selects); `moreFilters:`
# is the "More filters" drawer (three). Each row is `{ key: "…", …, options: [["v", "label"], …] }`
# on one line. If either block is restructured these patterns stop matching and the test fails
# loudly rather than silently testing nothing.
_BAR_BLOCK = re.compile(r"^      filters: \[\n((?:        \{ key: \"\w+\", options: \[.*\] \},?\n)+)      \]", re.MULTILINE)
_MORE_BLOCK = re.compile(r"^      moreFilters: \[\n((?:        \{ key: \"\w+\", label: \".*\", options: \[.*\] \},?\n)+)      \]", re.MULTILINE)
_ROW = re.compile(r"\{ key: \"(\w+)\",.*?options: \[(.*?)\] \}")
_OPTION = re.compile(r"\[\"([^\"]+)\", \"[^\"]*\"\]")

# What those patterns are expected to find. Retyped here on purpose: the regex catches a
# RESTRUCTURED design, this catches an option quietly added to or dropped from one.
EXPECTED_OPTIONS: dict[str, tuple[str, ...]] = {
    "type": ("Any", "Small animal", "Mixed", "Large animal", "Emergency", "Specialty"),
    "price": ("Any", "u500", "500-1000", "1000-2000", "o2000"),
    "revenue": ("Any", "u1000", "1000-2500", "o2500"),
    "doctors": ("Any", "1", "2", "4"),
    "building": ("Any", "Included", "Separate", "Leased"),
    "est": ("Any", "pre1995", "1995-2010", "post2010"),
    "ownership": ("Any", "Sole", "Multi"),
    "sqft": ("Any", "u3000", "3000-5000", "o5000"),
}


def design_filter_options() -> dict[str, tuple[str, ...]]:
    """The eight filters and their option values, read out of the design file."""
    src = LOGIC_JS.read_text(encoding="utf-8")
    found: dict[str, tuple[str, ...]] = {}
    for block in (_BAR_BLOCK, _MORE_BLOCK):
        match = block.search(src)
        assert match is not None, f"the design's filter block no longer matches {block.pattern!r}"
        for key, options in _ROW.findall(match.group(1)):
            found[key] = tuple(_OPTION.findall(options))
    return found


def design_matches(hospital: dict[str, object], key: str, value: str) -> bool:
    """One arm of `Component.filtered()` in frontend/src/logic.js, with the design's own band
    boundaries: price and revenue are divided by 1000; `u…` is strictly below; the middle bands
    are inclusive at both ends; `o…` is `>=`; doctors is "N or more"; ownership tests the
    ownership string for "Sole proprietor"; `post2010` is strictly after 2010."""
    if value == "Any":
        return True
    if key == "type":
        return hospital["type"] == value
    if key == "doctors":
        return not int(str(hospital["docs"])) < int(value)
    if key == "building":
        return hospital["bldg"] == value
    if key == "price":
        price = int(str(hospital["price"])) / 1000
        return {"u500": price < 500, "500-1000": 500 <= price <= 1000,
                "1000-2000": 1000 <= price <= 2000, "o2000": price >= 2000}[value]
    if key == "revenue":
        rev = int(str(hospital["rev"])) / 1000
        return {"u1000": rev < 1000, "1000-2500": 1000 <= rev <= 2500, "o2500": rev >= 2500}[value]
    if key == "est":
        est = int(str(hospital["est"]))
        return {"pre1995": est < 1995, "1995-2010": 1995 <= est <= 2010, "post2010": est > 2010}[value]
    if key == "ownership":
        solo = "Sole proprietor" in str(hospital["ownership"])
        return solo if value == "Sole" else not solo
    if key == "sqft":
        sqft = int(str(hospital["sqft"]))
        return {"u3000": sqft < 3000, "3000-5000": 3000 <= sqft <= 5000, "o5000": sqft >= 5000}[value]
    raise AssertionError(f"the design grew a filter this test does not implement: {key}")


def matching_slugs(key: str, value: str) -> list[str]:
    return [str(h["slug"]) for h in load() if design_matches(h, key, value)]


def test_the_design_still_declares_the_filters_this_test_covers() -> None:
    """The regex found the blocks, and the blocks hold exactly the options pinned above."""
    assert design_filter_options() == EXPECTED_OPTIONS


def test_every_non_any_filter_option_matches_at_least_one_hospital() -> None:
    """A-L2, the requirement itself — with the two options John excluded left out by name."""
    uncovered = [
        (key, value)
        for key, values in design_filter_options().items()
        for value in values
        if value != "Any" and (key, value) not in EXCLUDED_OPTIONS and not matching_slugs(key, value)
    ]
    assert uncovered == [], f"no seeded hospital matches {uncovered} — distribute the demo values"


def test_any_matches_all_eighteen_on_every_filter() -> None:
    for key, values in design_filter_options().items():
        assert "Any" in values, key
        assert len(matching_slugs(key, "Any")) == 18, key


def test_johns_ruling_still_holds_no_hospital_is_mixed_or_large_animal() -> None:
    """A-L2.2, pinned the other way round: John's answer was "they are all Small Animal", so the
    two excluded options must genuinely return nothing. If one of them ever matches, the
    exclusion has gone stale and the question goes back to John — it is not widened here."""
    assert JOHNS_RULING == "they are all Small Animal"
    for key, value in sorted(EXCLUDED_OPTIONS):
        assert matching_slugs(key, value) == [], (key, value, "John ruled the eighteen carry no such practice")


def test_the_excluded_options_are_exactly_the_two_john_named() -> None:
    """Pinned both ways so a future gap cannot be silenced by adding to the exclusion list."""
    assert EXCLUDED_OPTIONS == {("type", "Mixed"), ("type", "Large animal")}
    for key, value in EXCLUDED_OPTIONS:
        assert value in design_filter_options()[key], (key, value, "excluded an option the design no longer offers")
