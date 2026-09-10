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
    "status", "source", "location_disclosed", "name_disclosed", "rev_disclosed",
    "documents_disclosed", "lat", "lng", "geocode", "demo",
    "price", "rev", "docs", "rooms", "sqft", "bldg", "est", "listed_days_ago",
    "note", "staff", "services", "facility", "ownership",
}


def load() -> list[dict[str, object]]:
    """EVERY seeded hospital: John's eighteen of 2026-09-06 and his eleven Dallas rows of
    2026-09-10 (Task SD1). The two tables are separate contracts — different provenance, a
    different `area` meaning and five extra fields on the newer one — so a test that is about
    one of them says so through `johns_eighteen()` or `dallas_eleven()` below, and only a test
    that is genuinely about EVERY seed row reads this."""
    data = json.loads(SEEDS.read_text(encoding="utf-8"))
    assert data["version"] == 1
    hospitals = data["hospitals"]
    assert isinstance(hospitals, list)
    return hospitals


def johns_eighteen() -> list[dict[str, object]]:
    """The 2026-09-06 table, in file order — everything Task SD1 did not add."""
    return [h for h in load() if h["slug"] not in DALLAS_SLUGS]


def dallas_eleven() -> list[dict[str, object]]:
    """The 2026-09-10 Dallas table, in file order."""
    return [h for h in load() if h["slug"] in DALLAS_SLUGS]


def derived_type(name: str, hours: str) -> str:
    """D4, in the order D4 states it: Specialist wins over emergency hours."""
    if "Specialist" in name:
        return "Specialty"
    if "ER" in name.split() or "Critical Care" in name or "24/7 emergency" in hours:
        return "Emergency"
    return "Small animal"


def test_there_are_exactly_eighteen_hospitals() -> None:
    assert len(johns_eighteen()) == 18


def test_johns_table_is_reproduced_verbatim_and_in_order() -> None:
    rows = johns_eighteen()
    got = tuple((h["name"], h["city"], h["state"], h["street"], h["zip"], h["phone"], h["hours"]) for h in rows)
    assert got == JOHNS_TABLE


def test_every_hospital_carries_every_contracted_key() -> None:
    for h in johns_eighteen():
        assert set(h) == REQUIRED_KEYS, (h["slug"], set(h) ^ REQUIRED_KEYS)


def test_type_is_derived_exactly_as_d4_says() -> None:
    for h in johns_eighteen():
        assert h["type"] == derived_type(str(h["name"]), str(h["hours"])), h["slug"]


def test_the_derivation_produces_five_specialty_four_emergency_and_nine_small_animal() -> None:
    counts: dict[str, int] = {}
    for h in johns_eighteen():
        counts[str(h["type"])] = counts.get(str(h["type"]), 0) + 1
    assert counts == {"Specialty": 5, "Emergency": 4, "Small animal": 9}


# The two shapes John has written a fake number in: `(214) 555-0101` on the 2026-09-06 table and
# `214-555-0101` on the 2026-09-10 Dallas one. Both are the 555-01xx block reserved for fiction;
# neither is normalised, because his wording is the source of truth (A22's standing rule) and the
# number is rendered as he typed it. Anchored, so `1555-0101` or a 555 buried mid-number fails.
PHONE_SHAPES = re.compile(r"^(?:\(\d{3}\) |\d{3}-)555-01\d{2}$")


def test_every_phone_is_a_555_number() -> None:
    for h in load():
        assert PHONE_SHAPES.fullmatch(str(h["phone"])), (h["slug"], h["phone"])


def test_area_and_market_are_derived_from_the_city_and_state() -> None:
    for h in johns_eighteen():
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


def test_every_row_discloses_its_revenue_and_its_documents() -> None:
    """Task SL6, spec 2026-09-08 D22: "every seed sets all four disclosure flags true", so the
    buyer detail keeps showing the eighteen hospitals' revenue and their document count.

    `rev_disclosed` and `documents_disclosed` are added by migration 030 with a default of
    `false` — sellers hide by default — and backfilled there for the rows that already exist.
    A row INSERTED by a later seed run takes the default instead, so the value has to live in
    this file, and the two must not disagree."""
    for h in load():
        for flag in ("rev_disclosed", "documents_disclosed"):
            assert isinstance(h[flag], bool), (h["slug"], flag, type(h[flag]).__name__)
            assert h[flag] is True, (h["slug"], flag)


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
    slugs = [str(h["slug"]) for h in johns_eighteen()]
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
        for h in johns_eighteen()
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


def matching_slugs(key: str, value: str,
                   rows: list[dict[str, object]] | None = None) -> list[str]:
    """A-L2's coverage claim is about JOHN'S EIGHTEEN — the set that was distributed to cover
    every filter — so that is the default. Task SD1's eleven are passed in explicitly by the
    one test that is about them."""
    return [str(h["slug"]) for h in (johns_eighteen() if rows is None else rows)
            if design_matches(h, key, value)]


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
        assert len(matching_slugs(key, "Any", load())) == 29, key


def test_johns_ruling_still_holds_no_hospital_is_mixed_or_large_animal() -> None:
    """A-L2.2, pinned the other way round: John's answer was "they are all Small Animal", so the
    two excluded options must genuinely return nothing. If one of them ever matches, the
    exclusion has gone stale and the question goes back to John — it is not widened here."""
    assert JOHNS_RULING == "they are all Small Animal"
    for key, value in sorted(EXCLUDED_OPTIONS):
        assert matching_slugs(key, value) == [], (key, value, "John ruled the eighteen carry no such practice")
        assert matching_slugs(key, value, load()) == [], (key, value, "nor do the eleven")


def test_the_excluded_options_are_exactly_the_two_john_named() -> None:
    """Pinned both ways so a future gap cannot be silenced by adding to the exclusion list."""
    assert EXCLUDED_OPTIONS == {("type", "Mixed"), ("type", "Large animal")}
    for key, value in EXCLUDED_OPTIONS:
        assert value in design_filter_options()[key], (key, value, "excluded an option the design no longer offers")


def test_at_least_one_hospital_is_in_the_designs_default_market() -> None:
    """Final review M4. `logic.js` reads `MARKETS[s.market || "Austin, TX"].center` on EVERY
    render, and `frontend/src/listings/load.ts`'s `applyListings` deletes any market with no
    listing left — so a seed file with no Austin hospital is a blank app on QA, not a red test.
    A-L6.1 recorded this as latent for Wave 2b on the premise that the seed set contains Austin;
    this is that premise, pinned, because `seeds/hospitals.json` is a file John edits."""
    assert any(h["market"] == "Austin, TX" for h in load()), (
        "no hospital is in the design's default market; frontend/src/logic.js reads "
        'MARKETS["Austin, TX"].center on every render and applyListings would have dropped it'
    )


# ======================================================================================
# Task SD1 — John's Dallas table of 2026-09-10, and the provenance he attached to it.
#
# Eleven more seed hospitals in the market the eighteen already carry. Three things make them
# a SEPARATE contract from the 2026-09-06 table rather than eleven more rows of it:
#
#   * `area` is John's own "Area / market segment" column ("Far North / Preston corridor"),
#     not the bare city the eighteen carry. It is the community label the design shows as the
#     general location, and his segments are exactly that.
#   * `type` is a CONTROLLER RULING per row, not D4's name-and-hours derivation: Beta is a
#     specialty practice because John's own folder for it says so, and Indigo is an emergency
#     hospital because it is open around the clock though its name says neither.
#   * five provenance booleans record what is real and what is invented. They are DATA, never
#     UI: nothing renders them, and the reason they exist is that a real street address may
#     house a real and different business, so the file must say plainly that the address is a
#     seed anchor and the business identity is fictional.
#
# John's JSON named `address` and `postal_code`; the file has held `street` and `zip` for
# eighteen rows since 2026-09-06 and the loader reads those names, so the controller ruled the
# two renamed and NOTHING ELSE. `seeds/hospitals.json`'s own `note` records the mapping, and
# `test_the_note_records_the_field_mapping` below is what keeps it recorded.
# ======================================================================================

# (slug, name, area, street, zip, hours, phone) — John's table, verbatim, in his order. The en
# dashes in "Mon\u2013Fri" and "Dallas\u2013Fort Worth" are written `\u2013` for the same reason
# JOHNS_TABLE writes them that way: ruff's RUF001 has nothing to flag and the value is
# byte-identical to what he sent.
DALLAS_TABLE: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    ("alpha_dallas_veterinary_specialist_hospital", "Alpha Dallas Veterinary Specialist Hospital", "Far North / Preston corridor", "18770 Preston Rd", "75252", "Mon\u2013Fri 7:00 AM\u20136:00 PM; Sat 8:00 AM\u201312:00 PM; Sun closed", "214-555-0101"),
    ("beta_dallas_veterinary_hospital", "Beta Dallas Veterinary Hospital", "North / Forest Lane", "3452 Forest Ln, Ste 100", "75234", "Mon\u2013Fri 8:00 AM\u20135:30 PM; Sat 8:00 AM\u201312:00 PM; Sun closed", "214-555-0102"),
    ("charlie_dallas_animal_hospital", "Charlie Dallas Animal Hospital", "West Dallas / Oak Cliff", "1021 Fort Worth Ave", "75208", "Daily 8:00 AM\u20138:00 PM", "214-555-0103"),
    ("delta_dallas_animal_er_hospital", "Delta Dallas Animal ER Hospital", "South Dallas", "2944 E Illinois Ave", "75216", "24 hours / 7 days", "214-555-0104"),
    ("echo_dallas_animal_hospital", "Echo Dallas Animal Hospital", "Southwest Dallas", "3435 Marvin D. Love Fwy", "75224", "Mon\u2013Fri 8:00 AM\u20135:00 PM; Sat/Sun closed", "214-555-0105"),
    ("indigo_dallas_animal_hospital", "Indigo Dallas Animal Hospital", "North/East / Central Expressway", "11333 N Central Expy", "75243", "24 hours / 7 days", "214-555-0106"),
    ("foxtrot_dallas_animal_hospital", "Foxtrot Dallas Animal Hospital", "Highland Park / affluent central", "5075 McKinney Ave", "75205", "Mon\u2013Fri 8:00 AM\u20136:00 PM; Sat 8:00 AM\u201312:00 PM; Sun closed", "214-555-0107"),
    ("hotel_dallas_animal_hospital", "Hotel Dallas Animal Hospital", "East Dallas / Lakewood", "6363 Richmond Ave", "75214", "Mon\u2013Fri 7:30 AM\u20136:00 PM; Sat 8:00 AM\u201312:00 PM; Sun closed", "214-555-0108"),
    ("juliet_dallas_animal_hospital", "Juliet Dallas Animal Hospital", "East Dallas / Ferguson corridor", "8541 Ferguson Rd", "75228", "Mon 7:30 AM\u20138:00 PM; Tue 7:30 AM\u20136:00 PM; Wed 7:30 AM\u20136:00 PM; Thu 7:30 AM\u20138:00 PM; Fri 7:30 AM\u20136:00 PM; Sat 8:00 AM\u20132:00 PM; Sun closed", "214-555-0109"),
    ("kilo_dallas_fort_worth_veterinary_hospital", "Kilo Dallas\u2013Fort Worth Veterinary Hospital", "Southeast / Buckner", "2247 S Buckner Blvd, Ste 110", "75227", "Mon\u2013Sat 10:00 AM\u20132:00 PM; Sun closed", "214-555-0110"),
    ("lima_dallas_fort_worth_veterinary_hospital", "Lima Dallas\u2013Fort Worth Veterinary Hospital", "North Dallas / 75240", "13949 Peyton Dr", "75240", "Mon\u2013Fri 8:00 AM\u20135:30 PM; Sat 8:00 AM\u201312:00 PM; Sun closed", "214-555-0111"),
)

DALLAS_SLUGS = frozenset(row[0] for row in DALLAS_TABLE)

# John numbered his table 0101…0110 and left the eleventh blank. The controller INFERRED
# `214-555-0111` from that run and flagged it in the SD1 hand-back as an inference, not a fact.
# Pinned here so the inference is visible in the code as well as in the report: if John supplies
# a different number, this constant and the table above move together.
LIMA_PHONE_IS_INFERRED = "214-555-0111"

# CONTROLLER RULING (SD1 §1). Alpha is a specialist by name; Beta by John's own folder name
# ("Beta Dallas Veterinary Hospital Specialty & Emergency Care"), which is his statement of what
# it is; Delta is named ER and is open 24/7; Indigo is open 24/7. The other seven are small
# animal. D4's derivation is NOT used here — it would read Beta and Indigo as small-animal
# practices — so the map is written out and pinned instead.
DALLAS_TYPES: dict[str, str] = {
    "alpha_dallas_veterinary_specialist_hospital": "Specialty",
    "beta_dallas_veterinary_hospital": "Specialty",
    "charlie_dallas_animal_hospital": "Small animal",
    "delta_dallas_animal_er_hospital": "Emergency",
    "echo_dallas_animal_hospital": "Small animal",
    "indigo_dallas_animal_hospital": "Emergency",
    "foxtrot_dallas_animal_hospital": "Small animal",
    "hotel_dallas_animal_hospital": "Small animal",
    "juliet_dallas_animal_hospital": "Small animal",
    "kilo_dallas_fort_worth_veterinary_hospital": "Small animal",
    "lima_dallas_fort_worth_veterinary_hospital": "Small animal",
}

# John's provenance JSON, key for key. `address` and `postal_code` are the two the controller
# mapped onto the file's existing `street` and `zip`; everything else is carried verbatim, and
# these five are the new fields.
PROVENANCE_KEYS = frozenset({
    "phone_is_fake", "address_is_real", "address_is_seed_anchor",
    "business_identity_is_fictional", "operating_hours_is_seed_data",
})

# The two renames, as the file's own `note` must state them.
FIELD_MAPPING = (("address", "street"), ("postal_code", "zip"))

# A22 (John, 2026-09-10, "Preserve existing seed wording/detail"), read from the amendment
# itself rather than retyped: the wizard's ownership select carries exactly these ten, and a
# seed row whose `ownership` is not one of them is a value no seller could ever re-select.
AMENDMENTS_TS = ROOT / "frontend" / "tests" / "design-amendments.ts"
_A22_REPLACE = re.compile(
    r"id: 'A22'.*?replace: 'sel\(\"ownership\", \"Current ownership\", \[(.*?)\]\)'", re.DOTALL
)


def a22_ownership_options() -> tuple[str, ...]:
    """The ten options amendment A22 puts in the wizard, read out of `design-amendments.ts`."""
    match = _A22_REPLACE.search(AMENDMENTS_TS.read_text(encoding="utf-8"))
    assert match is not None, "amendment A22 no longer declares the ownership select"
    return tuple(re.findall(r'"([^"]+)"', match.group(1)))


def test_a22_still_declares_the_ten_ownership_options_this_file_reads() -> None:
    """The regex above found the amendment, and the amendment holds ten options. Without this
    a restructured A22 would make `a22_ownership_options()` return an empty tuple and the
    membership test below would pass by testing nothing."""
    options = a22_ownership_options()
    assert len(options) == 10, options
    assert options[0] == "Sole proprietor" and options[-1] == "Other", options


def test_there_are_exactly_eleven_dallas_hospitals() -> None:
    assert len(dallas_eleven()) == 11


def test_johns_dallas_table_is_reproduced_verbatim_and_in_order() -> None:
    got = tuple(
        (str(h["slug"]), str(h["name"]), str(h["area"]), str(h["street"]), str(h["zip"]),
         str(h["hours"]), str(h["phone"]))
        for h in dallas_eleven()
    )
    assert got == DALLAS_TABLE


def test_limas_phone_is_the_inferred_one_and_is_recorded_as_inferred() -> None:
    """John's numbering runs 0101…0110 in table order and Lima is the eleventh. The value is a
    controller inference; this pins it so the inference cannot become invisible."""
    lima = next(h for h in dallas_eleven() if h["slug"] == "lima_dallas_fort_worth_veterinary_hospital")
    assert lima["phone"] == LIMA_PHONE_IS_INFERRED
    assert DALLAS_TABLE[-1][6] == LIMA_PHONE_IS_INFERRED


def test_every_dallas_row_is_in_dallas_texas() -> None:
    for h in dallas_eleven():
        assert (h["city"], h["state"], h["market"]) == ("Dallas", "TX", "Dallas, TX"), h["slug"]


def test_the_dallas_area_is_johns_market_segment_not_the_bare_city() -> None:
    """SD1 §1: `area` is his "Area / market segment" column. The eighteen's `area` is the bare
    city and is NOT changed — it is not this task's — so the two conventions are pinned apart."""
    for h in dallas_eleven():
        assert h["area"] != h["city"], h["slug"]
    assert all(h["area"] == h["city"] for h in johns_eighteen())


def test_every_dallas_type_is_the_controllers_ruling() -> None:
    for h in dallas_eleven():
        assert h["type"] == DALLAS_TYPES[str(h["slug"])], h["slug"]


def test_the_dallas_types_are_two_specialty_two_emergency_and_seven_small_animal() -> None:
    counts: dict[str, int] = {}
    for h in dallas_eleven():
        counts[str(h["type"])] = counts.get(str(h["type"]), 0) + 1
    assert counts == {"Specialty": 2, "Emergency": 2, "Small animal": 7}


def test_no_dallas_type_is_outside_the_three_the_ruling_allows() -> None:
    """SD1 §1: "one of `Emergency`, `Small animal`, `Specialty`, no others"."""
    assert {str(h["type"]) for h in dallas_eleven()} <= {"Emergency", "Small animal", "Specialty"}


def test_every_dallas_row_carries_the_eighteens_keys_plus_the_five_provenance_booleans() -> None:
    for h in dallas_eleven():
        assert set(h) == REQUIRED_KEYS | PROVENANCE_KEYS, (h["slug"], set(h) ^ (REQUIRED_KEYS | PROVENANCE_KEYS))


def test_every_provenance_field_is_a_real_boolean_and_is_true() -> None:
    """John's JSON is the shape for all eleven and every one of its five booleans is `true`.
    `isinstance(..., bool)` matters: a truthy string would survive `is True`-less checks and
    reach the database as text."""
    for h in dallas_eleven():
        for key in sorted(PROVENANCE_KEYS):
            assert isinstance(h[key], bool), (h["slug"], key, type(h[key]).__name__)
            assert h[key] is True, (h["slug"], key)


def test_the_eighteen_did_not_gain_the_provenance_fields() -> None:
    """Surgical diff: the eleven are a new contract, the eighteen are untouched."""
    for h in johns_eighteen():
        assert PROVENANCE_KEYS.isdisjoint(set(h)), h["slug"]


def test_the_address_is_real_and_the_business_is_fictional_are_both_asserted() -> None:
    """The pair that must never drift apart. A real street address with no statement that the
    identity is invented is the reading John's ruling exists to prevent — a real building at
    18770 Preston Rd may house a real and different business."""
    for h in dallas_eleven():
        assert h["address_is_real"] is True and h["business_identity_is_fictional"] is True, h["slug"]
        assert h["address_is_seed_anchor"] is True, h["slug"]


def test_the_note_records_the_field_mapping() -> None:
    """CONTROLLER RULING: John's `address`/`postal_code` were mapped onto the file's existing
    `street`/`zip` and nothing else was renamed. The file's own `note` says so, so the next
    reader can see the JSON was mapped and not partially ignored."""
    note = str(json.loads(SEEDS.read_text(encoding="utf-8"))["note"])
    for johns_name, file_name in FIELD_MAPPING:
        assert johns_name in note and file_name in note, (johns_name, file_name, note)


def test_no_dallas_slug_collides_with_an_existing_one() -> None:
    slugs = [str(h["slug"]) for h in load()]
    assert len(set(slugs)) == len(slugs) == 29
    assert set(slugs) & PHOTO_FOLDER_SLUGS == PHOTO_FOLDER_SLUGS
    assert DALLAS_SLUGS.isdisjoint(PHOTO_FOLDER_SLUGS)


def test_every_dallas_slug_is_the_ascii_snake_case_of_its_name() -> None:
    """SD1 §1: snake_case, ASCII only, the en dash dropped — so "Kilo Dallas\u2013Fort Worth
    Veterinary Hospital" is `kilo_dallas_fort_worth_veterinary_hospital`, with no `u2013` and
    no double underscore where the dash was."""
    for h in dallas_eleven():
        slug = str(h["slug"])
        assert slug.isascii() and re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", slug), slug
        expected = re.sub(r"[^a-z0-9]+", "_", str(h["name"]).replace("\u2013", " ").lower()).strip("_")
        assert slug == expected, (slug, expected)


def test_every_dallas_ownership_is_one_of_a22s_ten() -> None:
    allowed = set(a22_ownership_options())
    for h in dallas_eleven():
        assert h["ownership"] in allowed, (h["slug"], h["ownership"])


def test_the_dallas_demo_values_are_varied_not_eleven_copies_of_one_row() -> None:
    """SD1 §1: "make them plausible and VARIED — do not clone one row eleven times"."""
    for field in ("price", "rev", "sqft", "est", "listed_days_ago", "staff", "services", "facility"):
        values = [h[field] for h in dallas_eleven()]
        assert len(set(map(str, values))) == 11, (field, values)


def test_a_round_the_clock_hospital_is_bigger_than_a_five_day_practice() -> None:
    """SD1 §1: "an emergency hospital open around the clock has more staff and more rooms than
    a five-day small-animal practice". Pinned as the floor of the 24/7 rows against the ceiling
    of the weekday-only ones, so the relationship survives an edit to any single row."""
    day = {str(h["slug"]): h for h in dallas_eleven()}
    round_clock = [h for h in day.values() if h["hours"] == "24 hours / 7 days"]
    weekday_only = [h for h in day.values() if "Sat/Sun closed" in str(h["hours"])]
    assert round_clock and weekday_only, "the hours strings no longer identify either group"
    assert min(int(str(h["rooms"])) for h in round_clock) > max(int(str(h["rooms"])) for h in weekday_only)
    assert min(int(str(h["docs"])) for h in round_clock) > max(int(str(h["docs"])) for h in weekday_only)


def test_every_dallas_row_satisfies_the_listing_check_constraints() -> None:
    """The bounds migrations 016, 030 and 034 impose, read here as data rather than by inserting:
    `listing_status_check` and `listing_type_check` (016, widened by 030), `bldg`'s own CHECK
    (016), `listing_submittable_ck` (030 — name, city, zip, type, est, price all present) and
    `listing_publishable_ck` (030, widened by 034 — a published row needs state, market, area
    AND sqft). `tests/scripts/test_seed_listings.py` proves the same eleven really insert."""
    for h in dallas_eleven():
        assert h["status"] in ("draft", "in_review", "published", "paused", "withdrawn", "declined"), h["slug"]
        assert h["type"] in ("Small animal", "Mixed", "Large animal", "Emergency", "Specialty", "Other"), h["slug"]
        assert h["bldg"] in ("Included", "Leased", "Separate"), h["slug"]
        assert h["source"] in ("seed", "seller"), h["slug"]
        for required in ("name", "city", "zip", "type", "est", "price"):        # submittable
            assert h[required] not in (None, ""), (h["slug"], required)
        for required in ("state", "market", "area", "sqft"):                    # publishable
            assert h[required] not in (None, ""), (h["slug"], required)


# --- M5: the demo prose may not be falsified by the photographs on the same page ---------------
#
# `facility`, `bldg`, `sqft` and `est` are demo values John may edit at any time — but not while
# the listing's own photographs say otherwise. A buyer reading "leased suite in a strip centre"
# beside a photograph of a detached clapboard building on open ground learns that the copy is
# not to be trusted, and that is a worse failure than a bland sentence.
#
# Five of the eleven were falsified by their own heroes and are corrected here; the other six
# were opened and are consistent. The corrected phrases are pinned as VALUES, and the four
# claims the photographs contradicted are pinned as FORBIDDEN so they cannot drift back in.

FACILITY_CORRECTED_AGAINST_THE_PHOTOGRAPHS = {
    # a pitched-roof building with a timber porch and a chimney — a converted house, not a shop
    "charlie_dallas_animal_hospital":
        "Converted house with a timber entrance porch on Fort Worth Avenue in Oak Cliff.",
    # a detached single-storey building with its own car park and standing sign, not a floor
    # of an office block (indigo_dallas_03/05/11 all show the whole building)
    "indigo_dallas_animal_hospital":
        "Detached single-storey building with its own car park and standing sign on North Central Expressway.",
    # a standalone with a decorative mission parapet, not an end unit in a row
    "juliet_dallas_animal_hospital":
        "Standalone building with a decorative parapet on Ferguson Road.",
    # a weathered detached building on its own fenced plot with a roadside pole sign
    "kilo_dallas_fort_worth_veterinary_hospital":
        "Detached single-storey building on its own fenced plot off South Buckner Boulevard, with a roadside pole sign.",
}

# What the photographs falsified. Substring, case-insensitive, across all eleven.
FACILITY_CLAIMS_THE_PHOTOGRAPHS_REFUTE = ("strip centre", "storefront", "office building", "end unit")

# FOXTROT IS THE COUNTER-EXAMPLE, and it is recorded because it nearly went the other way. Its
# hero (`foxtrot_dallas_01.png`) is a single-storey gable and I first "corrected" its prose to
# say so — but `foxtrot_dallas_03.png`, from the same folder, shows a clear upper row of windows
# above the entrance canopy. "Two-storey" was never falsified; the HERO was unrepresentative.
# The lesson, and the reason this comment is here rather than in a commit message: a facility
# claim is checked against the WHOLE folder, never against position 1 alone.
FOXTROT_IS_TWO_STOREY_IN_ITS_OWN_THIRD_PHOTOGRAPH = "foxtrot_dallas_03.png"


def test_the_four_falsified_facility_descriptions_are_corrected() -> None:
    rows = {str(h["slug"]): h for h in dallas_eleven()}
    for slug, expected in FACILITY_CORRECTED_AGAINST_THE_PHOTOGRAPHS.items():
        assert rows[slug]["facility"] == expected, slug


def test_no_dallas_facility_makes_a_claim_its_own_photographs_refute() -> None:
    """Pinned the other way round, so a future edit cannot quietly reintroduce one of the four."""
    offenders = [(str(h["slug"]), claim) for h in dallas_eleven()
                 for claim in FACILITY_CLAIMS_THE_PHOTOGRAPHS_REFUTE
                 if claim in str(h["facility"]).lower()]
    assert offenders == [], offenders


def test_charlies_founding_year_is_the_one_painted_on_its_own_wall() -> None:
    """Its hero photograph carries "EST. 2017" in the signage. A listing whose own building says
    2017 while the field says 2002 is the same defect as the facility prose, one field along."""
    charlie = next(h for h in dallas_eleven() if h["slug"] == "charlie_dallas_animal_hospital")
    assert charlie["est"] == 2017


def test_kilo_owns_the_detached_building_its_photographs_show() -> None:
    """`bldg` moves with the prose: the photographs show a detached building on its own fenced
    plot with a permanent pole sign and painted-on wall signage, which is not a leasehold suite.
    `sqft` 2150 is consistent with the single-storey footprint and is unchanged."""
    kilo = next(h for h in dallas_eleven() if h["slug"] == "kilo_dallas_fort_worth_veterinary_hospital")
    assert kilo["bldg"] == "Included"
    assert kilo["sqft"] == 2150
