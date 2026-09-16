"""Identity matching (spec 2026-09-09 C.5 step 3; directive 4 step 3).

The directive asks for exact, case-insensitive, punctuation- and whitespace-normalised, OCR-error-
tolerant, partial and abbreviation matching. Every row of the table below is one of those, and the
OCR-error rows are real substitutions a scene-text engine makes on signage: a serif I read as a 1, a
zero read as an O, an `rn` pair read as an `m`.

Fix round 1 (the P5 review): there is now ONE row per substitution pair, and each was measured red
with its pair deleted.

Fix round 2 (the P5 re-review): the address class is a table of its own -- `ADDRESS_ROWS` -- because
it is the class with two directions to get right at once, and prose is the one the re-review's M-H
put a ruling on. Every row records an ANSWER: a must-fire, a must-not-fire, a recorded
over-redaction (the safe direction, pinned so it cannot change unnoticed) or a recorded MISS."""
from __future__ import annotations

import json
import pathlib
from difflib import SequenceMatcher
from typing import Any

import pytest

from app.privacy import identity

ROOT = pathlib.Path(__file__).resolve().parents[2]

LISTING: dict[str, Any] = {
    "name": "Hill Country Animal Hospital",
    "street": "1204 Cypress Creek Rd",
    "city": "Cedar Park",
    "state": "TX",
    "zip": "78613",
    "phone": "(512) 555-0100",
    "slug": "hill-country-animal-hospital",
    # "walled" is the fixture's one `w`, and it is here so that `vv -> w` has a row of its own
    # (review I-2). It moved out of `services` in fix round 2, because the service vocabulary is
    # GENERIC now (re-review M-H) and a generic word is in no pool.
    "facility": "Two-storey brick building on Cypress Creek with a walled garden",
    "services": "Dentistry, surgery, boarding",
    "hours": "Mon-Fri 8-6",
}
EMAIL = "practice.manager@hillcountryvet.example"

#: A DIFFERENT practice, in a different metro, carrying none of this listing's terms. Every address
#: row is run against it as well as against LISTING (re-review I-A, verifier correction 3): against
#: LISTING a Cedar Park line is rescued by the `city` substring and by the `prose` token `cypress`,
#: so a regex-class answer measured only there is measuring the accident and not the class.
OTHER: dict[str, Any] = {"name": "Somewhere Else Veterinary", "city": "Dallas", "zip": "75001"}

# (the OCR line, the field it must match, the method it must match by)
#
# The METHOD column is derived, not chosen: `_compare` returns the FIRST method that fires, in the
# order exact -> substring -> token_set -> fuzzy, so each row records which of them actually
# explains that line under the normalisation below. It is not EXCLUSIVE -- a line can produce more
# than one Match, and three of these rows do (see `test_several_matches_on_one_line_is_normal`).
# Three rows are worth reading twice.
# "HILL COUNTRY ANIMAL HOSP" is a prefix of the normalised name, so `substring` fires before
# `token_set` ever runs; "ANIIVIAL" scores a token-set overlap of exactly 3/5 = 0.6, which is
# `>= TOKEN_SET`, so it is a token_set and not a fuzzy; and `fuzzy` is only ever reached by a line
# of two or more tokens whose overlap is BELOW 0.6, which is what "Cedar Parh" is for.
#
# The SUBSTITUTION block is one row per pair in `identity.SUBSTITUTIONS`, in the tuple's own order,
# and each was measured red with that one pair removed from the map (review I-2).
HITS = (
    ("Hill Country Animal Hospital", "name", "exact"),
    ("HILL COUNTRY ANIMAL HOSPITAL", "name", "exact"),                 # case
    ("Hill Country Animal Hospital.", "name", "exact"),                # punctuation
    ("Hill  Country   Animal Hospital", "name", "exact"),              # whitespace
    ("Welcome to Hill Country Animal Hospital", "name", "substring"),  # partial
    ("HILL COUNTRY ANIRNAL HOSPITAL", "name", "exact"),                # OCR: rn for M
    ("VVALLED", "prose", "distinctive"),                               # OCR: VV for W
    ("HILL C0UNTRY ANIMAL H0SPITAL", "name", "exact"),                 # OCR: 0 for O
    ("l204 Cypress Creek Rd", "street", "exact"),                      # OCR: l for 1
    ("HlLL COUNTRY ANIMAL HOSPITAL", "name", "exact"),                 # OCR: l for I
    ("S12 SSS-0100", "phone", "exact"),                                # OCR: S for 5
    ("7B613", "zip", "exact"),                                         # OCR: B for 8
    ("1Z04 Cypress Creek Rd", "street", "exact"),                      # OCR: Z for 2
    ("HILL COUNTRY ANIIVIAL HOSPITAL", "name", "token_set"),           # OCR: IVI for M -- 3/5 = 0.60
    ("HILL COUNTRY ANIMAL HOSP", "name", "substring"),                 # truncated by the sign's frame
    ("Cedar Parh", "city", "fuzzy"),                                   # OCR: h for k -- overlap 0.33, ratio 0.90
    ("Hill Country", "name", "distinctive"),                           # the sign's top line alone
    ("HCAH", "name", "abbreviation"),
    ("H.C.A.H.", "name", "abbreviation"),                              # dotted initials on a logo
    ("HC", "name", "abbreviation"),                                    # the second, generic-free arm
    ("1204 Cypress Creek Rd", "street", "exact"),
    ("Cedar Park", "city", "exact"),
    ("TX", "state", "exact"),                                          # `exact` has no length floor
    ("78613", "zip", "exact"),
    ("(512) 555-0100", "phone", "exact"),
    ("512.555.0100", "phone", "exact"),                                # punctuation again
    ("hillcountryvet.example", "email_domain", "exact"),
    ("hill-country-animal-hospital", "slug", "exact"),
)

# The two maintained vocabularies and the suffix table, restated. A parametrized walk over
# `identity.GENERIC`, `identity.URL_TLDS` or `identity.STREET_SUFFIXES` proves what each entry DOES
# and can never notice one going MISSING -- it simply runs one case fewer, which is measured:
# dropping `vet` from the TLD list, and `animal` from the generic set, each left the whole suite
# green. These are the other half of all three pins, so a removal is a deliberate edit in two files.
EXPECTED_GENERIC = frozenset({
    "animal", "hospital", "veterinary", "vet", "clinic", "pet", "care", "center", "centre",
    "of", "the", "and", "for", "dvm",
    # The service vocabulary (re-review M-H, controller ruling): a word that names what every
    # practice does identifies none of them, so it is in no pool and redacts nothing.
    "service", "services", "surgery", "surgical", "dentistry", "dental", "boarding", "grooming",
    "wellness", "exam", "exams", "vaccination", "vaccinations", "radiology", "pharmacy",
    "medicine", "emergency", "urgent", "diagnostics", "laboratory", "imaging",
})
EXPECTED_TLDS = ("com", "net", "org", "co", "us", "io", "info", "biz", "online", "pet", "vet",
                 "clinic", "care", "health")
EXPECTED_SUFFIXES = (
    "street", "st", "avenue", "ave", "road", "rd", "boulevard", "blvd", "drive", "dr",
    "lane", "ln", "parkway", "pkwy", "highway", "hwy", "freeway", "fwy",
    "expressway", "expy", "circle", "cir", "court", "ct", "place", "pl",
    "trail", "trl", "terrace", "ter", "plaza", "plz", "way", "loop", "row",
)
EXPECTED_WORD_SUFFIXES = ("dr", "ct", "court", "circle", "place", "way", "loop", "row")

# Which row of HITS pins which substitution pair, keyed by the pair's INPUT. Each was measured red
# with that one pair deleted from `identity.SUBSTITUTIONS` and the rest of the map left alone
# (review I-2), and the mapping is pinned both ways against the map itself below -- so a pair added
# without a case that proves it, or a row left behind by a pair that has gone, fails this file.
SUBSTITUTION_ROWS: dict[str, str] = {
    "rn": "HILL COUNTRY ANIRNAL HOSPITAL",
    "vv": "VVALLED",
    "0": "HILL C0UNTRY ANIMAL H0SPITAL",
    "1": "l204 Cypress Creek Rd",
    "i": "HlLL COUNTRY ANIMAL HOSPITAL",
    "5": "S12 SSS-0100",
    "8": "7B613",
    "2": "1Z04 Cypress Creek Rd",
}

# Lines that must NOT match anything, each with the reason it does not (review Minor 3: six of the
# seven rows used to return [] because they share no token with any term at all, which is not the
# reason the comment named). A matcher that fires on "Animal Hospital" would black out every
# photograph of every listing and teach sellers to remove masks. Both rules `_informative` enforces
# have a row here, because both were found by a review reading the matcher against this very table:
# "Animal Hospital" is two tokens that are BOTH generic, and "Cedar" is a single token of a
# two-token city. The three rows whose reason is a THRESHOLD or a GUARD have a test of their own
# below, so the reason is asserted and not merely written down here.
MISSES = (
    ("Animal Hospital", "two tokens, both generic: `_informative` refuses the substring arms"),
    ("Cedar", "one token of the two-token city: `_informative` refuses it"),
    ("VETERINARY CLINIC", "shares no token with any term, and both scores are far below their floors"),
    ("Open 7 days", "shares no token with any term"),
    ("(512) 555-9999", "the practice's own area code: overlap 0.5 < TOKEN_SET, ratio 0.667 < FUZZY"),
    ("OPEN", "short, alphabetic, upper case -- and not this practice's initials"),
    ("hcah", "the practice's own initials in LOWER case: signage shouts, and `isupper` is the test"),
    ("   ", "a blank line: `_compare`'s guard refuses an empty side"),
)

#: The service vocabulary, on a line of its own, must produce NO REGION AT ALL -- not a mask, not a
#: rectangle (re-review M-H, controller ruling: "prose/token matching NEVER fires on GENERIC service
#: words alone; only distinctive tokens redact"). A door labelled SURGERY identifies no practice,
#: and a seller shown a mask on it learns to remove masks, which is the failure the module's own
#: docstring names.
GENERIC_PROSE = (
    "Full-service veterinary hospital",
    "SURGERY",
    "Grooming & Boarding",
    "Wellness Exams",
    "Dentistry and dental care",
    "24/7 Emergency and urgent care",
)

# ---------------------------------------------------------------------------------------------
# The address class. (line, expected regex:address, why)
#
# `fires` is the ANSWER, and the third column says which kind of answer it is. Four kinds:
#   MUST      a street address a member would meet, and the class exists to find it.
#   TITLE     the title "Doctor", which is not an address (controller ruling on Minor 8).
#   OVER      a recorded OVER-redaction: it fires, it should not, and the safer direction is ruled
#             acceptable -- pinned here so it cannot change unnoticed rather than left unstated.
#   MISS      a recorded UNDER-redaction the class deliberately does not reach; P7's line
#             aggregation is where a wrapped address is rejoined, and the regex is not widened here.
# ---------------------------------------------------------------------------------------------
ADDRESS_ROWS: tuple[tuple[str, bool, str], ...] = (
    # --- the shapes fix round 1's narrowing lost, restored by the anchored house-number arm (I-A)
    ("1204 Cypress Creek Dr Cedar Park TX", True, "MUST: house number, Dr, city, no comma"),
    ("400 Oak Dr Round Rock TX", True, "MUST: the review's own probe line"),
    ("400 Oak Dr Round Rock, TX", True, "MUST: the same with the comma OCR drops first"),
    ("4410 Bee Cave Dr Austin TX", True, "MUST"),
    ("22 Oak Dr Cedar Park", True, "MUST: no state"),
    ("1204 CYPRESS CREEK DR CEDAR PARK TX", True, "MUST: painted signage shouts"),
    ("1204 Cypress Creek Dr. Cedar Park TX", True, "MUST: the abbreviation's period"),
    ("1204 Cypress Creek Dr 78613", True, "MUST: a ZIP rather than a city"),
    ("  1204 Cypress Creek Dr Cedar Park TX", True, "MUST: the engine's own leading padding"),
    # --- and the shapes that always fired, which the anchored arm must not disturb
    ("1204 Cypress Creek Dr", True, "MUST: the suffix ends the line"),
    ("1204 Cypress Creek Dr, Cedar Park TX", True, "MUST: a comma after the suffix"),
    ("1204 Cypress Creek Drive Cedar Park", True, "MUST: the spelled-out twin"),
    ("1204 Cypress Creek Rd", True, "MUST: the control"),
    ("1204 Cypress Creek Rd Cedar Park TX", True, "MUST: an unambiguous suffix needs no guard"),
    ("Located at 1204 Cypress Creek Rd Cedar Park", True, "MUST: a mid-line number, plain suffix"),
    # --- I-B: the suffixes the alternation omitted (USPS top-15 plus the seeds' own)
    ("1204 Cypress Way", True, "MUST"), ("1204 Cypress Ct", True, "MUST"),
    ("1204 Cypress Cir", True, "MUST"), ("1204 Cypress Pl", True, "MUST"),
    ("1204 Cypress Trl", True, "MUST"), ("1204 Cypress Loop", True, "MUST"),
    ("1204 Cypress Ter", True, "MUST"), ("1204 Cypress Plz", True, "MUST"),
    ("1204 Cypress Court", True, "MUST"), ("1204 Cypress Circle", True, "MUST"),
    ("1204 Cypress Place", True, "MUST"), ("1204 Cypress Trail", True, "MUST"),
    ("1204 Cypress Terrace", True, "MUST"), ("1204 Cypress Plaza", True, "MUST"),
    ("2080 Principal Row", True, "MUST: a seed street"),
    ("8042 Katy Freeway", True, "MUST: a seed street"),
    ("11333 N Central Expy", True, "MUST: a seed street"),
    ("3435 Marvin D. Love Fwy", True, "MUST: a seed street, with an initial's period"),
    ("400 Oak Way Round Rock TX", True, "MUST: an English-word suffix, house-number led"),
    ("2 St Marys Way", True, "MUST"),
    ("4140 FM 1431", True, "MUST: a Texas farm-to-market road -- the designator PRECEDES its number"),
    ("2600 RR 620 S", True, "MUST: a ranch road"),
    # --- M-G: a unit letter on the house number
    ("1204B Cypress Creek Rd", True, "MUST: a unit letter glued to the house number"),
    ("1204-B Cypress Creek Rd", True, "MUST: a unit letter hyphenated to it"),
    # --- M-F: the suite arm, tightened to a unit rather than any word
    ("Suite 210", True, "MUST: a directory board with no street number in front of it"),
    ("Ste. 4", True, "MUST"), ("Suite B", True, "MUST: a single-letter unit"),
    ("Full suite of dental services", False, "TITLE-class: the English word `suite` on a poster"),
    ("A complete suite of wellness plans", False, "TITLE-class: the same, on marketing copy"),
    # --- the title "Doctor": the controller's ruling on Minor 8, in every written form
    # `Dr Rachel Mendes` carries NO DIGIT, so the house-number term refuses it and the parent
    # pattern refused it too (re-review M-P): it is the ruling's own contract row and it pins the
    # lookahead in no way at all -- the two digit-bearing rows below are what pin that.
    ("Dr Rachel Mendes", False, "TITLE: the ruling's own example -- no digit, refused by the parent too"),
    ("Dr. Rachel Mendes", False, "TITLE: the period spelling, no digit"),
    ("DR MENDES", False, "TITLE: shouted"),
    ("Open 7 days with Dr Jones", False, "TITLE: pins the trailing guard"),
    ("Open 7 days with Dr. Jones", False, "TITLE: pins the guard's period arm (M-A)"),
    ("24/7 Emergency Dr Smith", False, "TITLE: pins the trailing guard"),
    ("24/7 Emergency Dr. Smith", False, "TITLE: pins the guard's period arm (M-A)"),
    ("2 Dr Jones", False, "TITLE: a street NAME is required between number and suffix"),
    ("1 Dr Rachel Mendes", False, "TITLE"),
    ("2024 Dr. Rachel Mendes DVM", False, "TITLE: an established-in year before the title"),
    ("101 Dr Smith", False, "TITLE"),
    ("1st Floor Dr Mendes", False, "TITLE: `1st` is no house number -- no space after the digits"),
    ("Room 3 Dr Smith", False, "TITLE"),
    ("Est 1998 Dr Jones", False, "TITLE"),
    # --- other lines that are not addresses
    ("EST. 2017", False, "an established-in year"),
    ("EXAM ROOM 1", False, "a room number"),
    ("Dog Treats 10 ct", False, "a pack count: no street name between the number and the token"),
    ("3 Ways to Save", False, "`Ways` is not `way` -- the word boundary refuses it"),
    ("Cypress Creek Rd", False, "no house number: spec C.5 step 2's class begins with one"),
    # --- OVER: recorded over-redaction, ruled acceptable as the safer direction
    ("2 Vets Dr Mendes", True, "OVER: a number-first line with a word before the title"),
    ("24 Hour Emergency Dr Smith", True, "OVER: the same shape"),
    ("7 days a week Dr Jones", True, "OVER: the same shape"),
    ("3 Locations Dr Mendes", True, "OVER: the same shape"),
    ("16 slice CT", True, "OVER: a CT scanner, read as a court"),
    ("1 Stop Pet Place", True, "OVER: an English-word suffix ending a slogan"),
    ("3 exam rooms in one place", True, "OVER: the same"),
    ("24 hour care the right way", True, "OVER: the same"),
    ("Est. 1998 in this place", True, "OVER: the same, mid-line"),
    # --- MISS: recorded under-redaction the class deliberately does not reach
    ("Located at 1204 Cypress Creek Dr Cedar Park", False,
     ("MISS: a mid-line house number with an English-word suffix -- the guard refuses it and `\\A` "
      "cannot see it; P7's line aggregation is where a wrapped address is rejoined")),
    ("I204 Cypress Creek Rd", False,
     ("MISS: an OCR-confused leading digit -- `\\b\\d+` cannot start inside the token, and the "
      "substitution fold that rescues the listing's OWN address runs on normalised text only")),
)

#: The joined pass over the address class: a wrapped address, and the one wrap the anchor cannot
#: reach (re-review I-A residual 3).
WRAPPED_ADDRESS: tuple[tuple[tuple[str, ...], list[int], str], ...] = (
    (("1204 Cypress", "Creek Dr Cedar Park TX"), [0, 1], "MUST: the joined text begins with the number"),
    (("1204 Cypress", "Creek Rd Cedar Park TX"), [0, 1], "MUST: the unambiguous twin"),
    (("Hill Country Animal Hospital", "1204 Cypress", "Creek Rd Cedar Park TX"), [1, 2],
     "MUST: a plain suffix needs no anchor"),
    (("Hill Country Animal Hospital", "1204 Cypress", "Creek Dr Cedar Park TX"), [],
     ("MISS: `\\A` holds at the JOINED string's start, so a bare-Dr address BELOW a header line is "
      "not reached; P7's aggregation is where that is rejoined")),
)

#: `phone`'s separators, which were a SINGLE optional character (re-review M-B). Each of these is a
#: real shape: a number wrapped at its own hyphen, an internal double space no strip collapses, and
#: van lettering with spaced hyphens.
PHONE_SHAPES: tuple[tuple[tuple[str, ...], list[int]], ...] = (
    (("(512) 555-", "0100"), [0, 1]),
    (("512-555-", "0100"), [0, 1]),
    (("(512)  555-0100",), [0]),
    (("512 - 555 - 0100",), [0]),
    (("512 -", "555 - 0100"), [0, 1]),
)


@pytest.mark.parametrize(("line", "field", "method"), HITS)
def test_every_contracted_match_is_found_by_its_contracted_method(line: str, field: str, method: str) -> None:
    found = identity.matches([line], LISTING, EMAIL)
    assert [(m.field, m.method) for m in found if m.field == field] != [], found
    assert any(m.field == field and m.method == method for m in found), found
    assert all(0.0 <= m.score <= 1.0 and m.line == 0 for m in found)


@pytest.mark.parametrize(("line", "why"), MISSES)
def test_a_generic_or_foreign_line_matches_no_identity_field(line: str, why: str) -> None:
    assert [m for m in identity.matches([line], LISTING, EMAIL) if m.method != "regex"] == [], why


@pytest.mark.parametrize("line", GENERIC_PROSE)
def test_a_line_of_service_words_alone_is_no_region_at_all(line: str) -> None:
    """The controller's ruling on re-review M-H: prose and token matching NEVER fire on generic
    service words alone -- "full-service veterinary hospital" is a description of every practice in
    the country, not the identity of one -- and only DISTINCTIVE tokens redact.

    Before it, every distinctive token of the seller's `services` text masked interior signage
    naming that service: a door labelled SURGERY, a poster reading "Wellness Exams". The fix is at
    the source, in `GENERIC`, because `_pool` and `_informative` both read it: the words are in no
    pool, so no rectangle is drawn anywhere on the photograph."""
    assert identity.matches([line], LISTING, EMAIL) == []


def test_every_substitution_pair_has_a_row_and_the_map_reaches_one_fixed_point() -> None:
    """Two properties, and the second is why the order the comment used to call load-bearing is not.

    Pinned BOTH ways against `SUBSTITUTION_ROWS`: a pair added to the map without a row that proves
    it fails here rather than passing silently, and a row left behind by a pair that has gone fails
    here too (review I-2: six of the eight could be deleted with the whole suite green). And no
    pair's OUTPUT character is any pair's INPUT -- `m w o l s b z` against `rn vv 0 1 i 5 8 2` -- so
    the map reaches one fixed point whatever order it is applied in, which is exactly what makes
    folding BOTH sides of a comparison safe."""
    assert set(SUBSTITUTION_ROWS) == {wrong for wrong, _right in identity.SUBSTITUTIONS}
    assert set(SUBSTITUTION_ROWS.values()) <= {line for line, _field, _method in HITS}
    inputs = {ch for wrong, _right in identity.SUBSTITUTIONS for ch in wrong}
    outputs = {ch for _wrong, right in identity.SUBSTITUTIONS for ch in right}
    assert inputs & outputs == set()


@pytest.mark.parametrize(("line", "cls"), [
    ("Call (512) 555-0100 today", "phone"),
    ("visit hillcountryvet.com", "url"),
    ("https://vetbook.example/hc", "url"),
    ("hello@somewhere.example", "email"),
    ("1204 Cypress Creek Rd", "address"),
    ("Suite 210", "address"),
    ("4140", "premises_number"),
    ("22113", "premises_number"),
    ("2101", "premises_number"),
    ("@hillcountryvet", "handle"),
    ("78613", "zip"),
])
def test_a_regex_class_is_an_identifying_region_whether_or_not_it_matches_the_listing(
    line: str, cls: str
) -> None:
    """Spec C.5 step 2: "each hit is an identifying region regardless of matching". A phone number
    that is not this practice's is still a phone number in a photograph of it. The three
    `premises_number` rows are the strings the Dallas seed photographs actually hold (A-IDP-7),
    Juliet's divergent `22113` included -- a number worn as signage belongs to no column of this
    listing or any other, which is exactly why the identity matcher can never reach it.

    Every regex Match carries score 1.0 (re-review M-K): P7 reads the score, and a class either
    fired or it did not -- there is no partial regex hit."""
    found = identity.matches([line], OTHER, None)
    assert any(m.field == f"regex:{cls}" and m.method == "regex" for m in found)
    assert all(m.score == 1.0 for m in found if m.method == "regex")


@pytest.mark.parametrize(("line", "fires", "why"), ADDRESS_ROWS)
def test_the_address_class_answers_each_shape_the_way_it_is_ruled_to(line: str, fires: bool, why: str) -> None:
    """The address class, against a listing that shares nothing with these lines.

    Run against OTHER and not LISTING (re-review I-A, verifier correction 3): against LISTING a
    Cedar Park line is rescued by the `city` substring and by the `prose` token `cypress`, so a
    regex answer measured there is measuring the accident. `street` is NEVER seller-written
    (`app/api/seller_listings.py`), so on a real listing there is no street term at all and this
    class is the only thing that reads a street address off a photograph."""
    found = [m for m in identity.matches([line], OTHER, None) if m.field == "regex:address"]
    assert bool(found) is fires, f"{why}: {found}"


@pytest.mark.parametrize(("lines", "expected", "why"), WRAPPED_ADDRESS)
def test_a_wrapped_address_is_a_region_on_every_line_its_span_touches(
    lines: tuple[str, ...], expected: list[int], why: str
) -> None:
    found = identity.matches(list(lines), OTHER, None)
    assert sorted(m.line for m in found if m.field == "regex:address") == expected, why


@pytest.mark.parametrize("street", [
    h["street"] for h in json.loads((ROOT / "seeds" / "hospitals.json").read_text())["hospitals"]
])
def test_every_seed_hospitals_street_is_an_address_region(street: str) -> None:
    """The repository's own 29 demo streets, read as ANOTHER premises' sign (re-review I-B).

    Seven of them fired no class at all before this round -- `2080 Principal Row`,
    `9801 Old Winery Place`, `1700 Century Cir NE`, `4434 Frontier Trail`, `8042 Katy Freeway`,
    `3435 Marvin D. Love Fwy`, and `11333 N Central Expy` only by the five-digit `zip` accident --
    which is 24 % of John's real-address demo hospitals. Walked off a DIFFERENT listing so that a
    seed added on a new suffix fails on the day it is added rather than on the day somebody looks."""
    assert [m for m in identity.matches([street], OTHER, None) if m.field == "regex:address"] != []


@pytest.mark.parametrize("suffix", identity.STREET_SUFFIXES)
def test_every_street_suffix_in_the_table_is_an_address_region(suffix: str) -> None:
    """The `URL_TLDS` seam idiom applied to the street types (re-review I-B): the table IS the seam,
    and every entry is proved to fire rather than merely declared."""
    assert [m for m in identity.matches([f"1204 Cypress {suffix}"], OTHER, None)
            if m.field == "regex:address"] != []


@pytest.mark.parametrize(("line", "cls"), [
    ("hello@somewhere.example", "handle"),   # `handle`'s (?<!\w): an email address is not a handle
    ("123456", "zip"),                       # `zip`'s trailing (?!\d): six digits are not a code
    ("51255501001", "phone"),                # `phone`'s leading (?<!\d): eleven digits are not one
    ("Meet us @ the clinic", "handle"),      # a bare @ with a space after it
    ("Ref 512 555 010", "phone"),            # nine digits
    ("$1,234,567", "phone"),                 # a price, not a number
    ("Since 12.05.2010", "phone"),           # a date
])
def test_a_regex_class_refuses_the_near_miss_its_own_guard_exists_for(line: str, cls: str) -> None:
    """Three of the seven classes carry a boundary guard whose removal the suite could not see
    (review §4's survivor table): `handle`'s `(?<!\\w)`, `zip`'s trailing `(?!\\d)` and `phone`'s
    leading `(?<!\\d)`. Each is over-redaction when it goes -- an email address becoming a handle, a
    six-digit part number becoming a postal code -- so each gets the row that makes it provable. The
    last two rows hold while `phone`'s inner separators are widened (re-review M-B)."""
    assert [m for m in identity.matches([line], LISTING, EMAIL) if m.field == f"regex:{cls}"] == []


@pytest.mark.parametrize("tld", identity.URL_TLDS)
def test_every_tld_in_the_maintained_list_is_a_bare_domain(tld: str) -> None:
    """Spec C.5 step 2 asks for "a maintained TLD list" and there was no seam and no test: five
    real TLDs a practice uses -- `.co`, `.us`, `.io`, `.info`, `.pet` -- fired nothing without a
    scheme or a `www.` (review Minor 7), and `.biz`/`.online` joined them in fix round 2 (re-review
    M-J). `URL_TLDS` is the seam, this walks every entry of it, and `example` is deliberately
    absent: it is RFC 2606's documentation TLD, belongs to no practice, and a production class that
    recognised it would be a class tuned to the fixtures."""
    assert "example" not in identity.URL_TLDS
    line = f"visit hillcountryvet.{tld} today"
    assert any(m.field == "regex:url" for m in identity.matches([line], LISTING, EMAIL)), line


def test_the_three_maintained_vocabularies_are_pinned_both_ways() -> None:
    """A parametrized walk over a table proves what each entry DOES and can never notice one going
    MISSING: it simply runs one case fewer, which is measured -- dropping `vet` from the TLD list,
    and `animal` from the generic set, each left the whole suite green. This is the other half of
    all three pins, so a removal is a deliberate edit in two files and an addition arrives beside
    the case that proves it."""
    assert identity.GENERIC == EXPECTED_GENERIC
    assert identity.URL_TLDS == EXPECTED_TLDS
    assert identity.STREET_SUFFIXES == EXPECTED_SUFFIXES
    assert identity.WORD_SUFFIXES == EXPECTED_WORD_SUFFIXES
    assert set(identity.WORD_SUFFIXES) <= set(identity.STREET_SUFFIXES)


def test_the_glued_word_url_is_a_recorded_over_redaction() -> None:
    """The bare-TLD list means an OCR-glued sentence end reads as a domain: `Contact.us`,
    `Find.info`, `Emergency.Pet` (re-review M-E). Over-redaction only -- the seller removes the
    mask -- and it is the price of catching a practice's bare domain with no scheme in front of it,
    so it is recorded here as the deliberate answer rather than left unstated."""
    for line in ("Contact.us today", "Find.info here", "24/7 Emergency.vet"):
        assert any(m.field == "regex:url" for m in identity.matches([line], OTHER, None)), line


@pytest.mark.parametrize("line", ["EST. 2017", "EXAM ROOM 1", "24/7", "Open 7 days", "1", "1234567"])
def test_a_line_that_is_not_only_a_number_is_not_a_premises_number(line: str) -> None:
    """`premises_number` is deliberately WHOLE-LINE and two to six digits (A-IDP-7), so an interior
    is not blanketed: an established-in year, a room number and an opening-hours pill all carry
    other tokens, and a single digit is too short. Where a number DOES share a line with the
    practice's own name, the identity match already makes that whole line one region. The
    seven-digit row pins the UPPER bound, which `\\d{2,7}` could widen with the suite green
    (re-review M-K)."""
    assert [m for m in identity.matches([line], LISTING, EMAIL)
            if m.field == "regex:premises_number"] == []


@pytest.mark.parametrize(("lines", "expected"), [
    (["(512)", "555-0100"], [0, 1]),
    (["(512) ", "555-0100"], [0, 1]),      # the engine's own trailing space (review I-1)
    (["(512)", " 555-0100"], [0, 1]),      # ... and its leading one
    (["(512)", "", "555-0100"], [0, 2]),   # a blank line between the halves joins no space at all
    (["Call", "us", "on", "(512)", "555-0100"], [3, 4]),   # five lines: the span arithmetic itself
    (["(512)", "555-0100", "Cedar", "Park"], [0, 1]),      # ... and text AFTER it (re-review M-L)
])
def test_a_number_split_across_two_lines_is_still_a_hit_on_both_of_them(
    lines: list[str], expected: list[int]
) -> None:
    """Spec C.5 step 2 runs the regex classes "over every line and over the joined text". Scene text
    wraps: an area code on one line of a sign and the rest on the next is a telephone number no
    per-line pass can see, and the aggregator needs BOTH lines so the fill covers both halves rather
    than one rectangle spanning the gap between them.

    The padded rows are review I-1, and they were red: `app/privacy/ocr.py` takes the engine's text
    verbatim, so `"(512) "` arrives as readily as `"(512)"`, and one character of padding made the
    join a DOUBLE space that `phone`'s single-character separator class cannot cross -- the number
    was then a region on neither line, which is under-redaction in the exact case this pass exists
    for. A blank line contributes no separator at all and is attributed nothing.

    The last two rows are the span ARITHMETIC in both directions (review §4; re-review M-L). With
    four separators the drift of a +1 accumulates and line 2 -- holding no part of the number -- is
    drawn in; with text AFTER the number a -1 drift does the same to `Cedar`. On two lines neither
    is visible, which is why the rows are five and four lines long."""
    found = identity.matches(lines, LISTING, EMAIL)
    assert sorted(m.line for m in found if m.field == "regex:phone") == expected
    # and no line matched it on its own -- neither half is ten digits
    for half in lines:
        assert [m for m in identity.matches([half], LISTING, EMAIL) if m.field == "regex:phone"] == []


@pytest.mark.parametrize(("lines", "expected"), PHONE_SHAPES)
def test_a_number_broken_by_more_than_one_separator_is_still_a_number(
    lines: tuple[str, ...], expected: list[int]
) -> None:
    """`phone`'s inner separators were a SINGLE optional character, so three real shapes were no
    telephone number at all (re-review M-B): a number WRAPPED at its own hyphen (the join then adds
    a second separator), an internal double space on one line -- which never reaches the joined pass
    at all, because `regex_hits` returns early for a single line and the strip does not collapse
    internal whitespace -- and van lettering with spaced hyphens. The listing's OWN number is caught
    in every one of these by `phone/exact`, because normalisation folds the punctuation; the loss
    was a third party's number, which is exactly what this class exists for."""
    found = identity.matches(list(lines), OTHER, None)
    assert sorted(m.line for m in found if m.field == "regex:phone") == expected


def test_a_joined_hit_is_recorded_once_per_line_and_not_twice() -> None:
    """The per-line pass and the joined pass see the same match; the record carries one entry,
    because `identity_matches` indexes into `ocr.lines` and a duplicate would make the same region
    twice.

    TWO lines, not one (review I-3a): `regex_hits` returns before the joined pass runs at all when
    `len(lines) < 2`, so the single-line version of this test could not reach the dedup it is named
    for -- with the dedup removed it stayed green, while two lines record `regex:phone` on line 0
    twice."""
    found = [m for m in identity.matches(["Call (512) 555-0100 today", "Cedar Park TX"], LISTING, EMAIL)
             if m.field == "regex:phone"]
    assert [m.line for m in found] == [0]


def test_two_wrapped_numbers_record_the_shared_line_once() -> None:
    """`seen.add` INSIDE the joined loop, which nothing saw (re-review M-M). A sign wraps two
    telephone numbers over three lines; no line is a number on its own; the joined text holds two,
    and both touch line 1. Without the add inside the loop line 1 is recorded twice -- the
    duplicated `identity_matches` entry and the duplicated rectangle I-3a's contract forbids."""
    lines = ["(512)", "555-0100 (512)", "555-0199"]
    found = [m for m in identity.matches(lines, OTHER, None) if m.field == "regex:phone"]
    assert [m.line for m in found] == [0, 1, 2]


def test_the_joined_pass_can_compose_a_number_out_of_two_lines_that_are_not_one() -> None:
    """`["Room 210", "555-0100"]` joins to a string that IS a ten-digit telephone number, and both
    lines become regions though neither is a number (review Minor 11). Over-redaction, and inherent
    to the joined pass that is the only way to cover a wrapped number at all -- so it is recorded
    here as the deliberate answer rather than removed, and P7 is told in the report."""
    found = identity.matches(["Room 210", "555-0100"], LISTING, EMAIL)
    assert sorted(m.line for m in found if m.field == "regex:phone") == [0, 1]


def test_only_the_email_domain_is_ever_read() -> None:
    """Data minimisation (spec C.5 step 3): the part before the @ is a person's name as often as
    not, and no photograph of a building contains it.

    The domain is stored NORMALISED, like every other term -- `hillcountryvet.example` folds to
    `hlllcountryvet example` under the substitution map -- so the assertion is against that
    spelling. Asserting the raw address would fail against a correct matcher, which is the sort of
    row that gets a working rule "fixed"."""
    terms = identity.identity_terms(LISTING, EMAIL)
    assert terms["email_domain"] == [identity.normalise("hillcountryvet.example")]
    assert "manager" not in str(terms)


def test_the_seller_prose_fields_contribute_tokens_and_never_whole_string_matches() -> None:
    """`facility`, `services` and `hours` are free text: matching a whole sentence would fire on
    nothing, and matching every word in them would fire on everything. Distinctive tokens only.

    The first assertion is on the WHOLE list and on the NORMALISED name (review I-3b). The raw
    sentence it used to look for could never have been in `terms["name"]`, because every term is
    normalised before it is stored -- so adding `normalise(facility)` to that very list left the
    test green, which is a test that cannot fail."""
    terms = identity.identity_terms(LISTING, EMAIL)
    assert terms["name"] == [identity.normalise(LISTING["name"])]
    assert any("cypress" in t for t in terms["prose"])
    assert not any(t in ("mon", "fri", "8", "6") for t in terms["tokens"] + terms["prose"])
    # the whole `services` field is generic now, so it contributes nothing at all (M-H)
    assert not any(t in ("surgery", "dentlstry", "boardlng") for t in terms["prose"])


def test_a_prose_token_is_recorded_as_prose_and_never_as_the_practice_name() -> None:
    """The privacy row's `identity_matches` names a COLUMN to whoever reads it, and a long word out
    of `facility` is not the practice's name: the line "Dentistry" was recorded as `name` (review
    Minor 9). The two pools are separate and each carries its own field."""
    assert [(m.field, m.method) for m in identity.matches(["Storey"], LISTING, EMAIL)] \
        == [("prose", "distinctive")]
    assert [(m.field, m.method) for m in identity.matches(["Hill Country"], LISTING, EMAIL)] \
        == [("name", "distinctive"), ("name", "substring"), ("slug", "substring")]
    terms = identity.identity_terms(LISTING, EMAIL)
    assert terms["tokens"] == ["country"]
    assert set(terms["tokens"]) & set(terms["prose"]) == set()


def test_a_token_in_both_pools_belongs_to_the_name_and_is_reported_once() -> None:
    """`prose` is the DIFFERENCE and not the union, and nothing saw it (re-review M-C): the
    fixture's one name token occurs in no prose field, so the set-intersection assertion above
    cannot fail. A practice called "Cypress Vet" whose facility text also says Cypress must produce
    ONE match, labelled `name` -- the union gives two, the same rectangle twice for P7, which is the
    class the distinctive `break` is pinned against."""
    both: dict[str, Any] = {"name": "Cypress Vet", "facility": "Cypress Creek plaza"}
    assert [(m.field, m.method) for m in identity.matches(["Cypress"], both, None)] \
        == [("name", "distinctive")]
    assert identity.identity_terms(both, None)["prose"] == ["creek", "plaza"]


def test_a_line_carrying_two_distinctive_tokens_is_one_match_and_not_two() -> None:
    """The `break` in the distinctive pass (review §4's survivor table). "Cypress Creek" carries two
    tokens of the prose pool, and without the break each would append its own Match -- a duplicated
    `identity_matches` entry and, for P7, the same rectangle twice. One distinctive hit per pool per
    line is the contract; the `street` substring beside it is a different field and belongs."""
    assert [(m.field, m.method) for m in identity.matches(["Cypress Creek"], LISTING, EMAIL)] \
        == [("prose", "distinctive"), ("street", "substring")]


def test_several_matches_on_one_line_is_normal_and_the_table_is_not_exclusive() -> None:
    """The HITS table's METHOD column names A method that explains the line, never the only one
    (report D5, review §7 note 2). `slug` duplicates `name` whenever the slug is the name, and a
    `distinctive` hit rides along with `substring` and `exact`. P7's union must assume many-to-one:
    nothing in this module de-duplicates ACROSS fields, only `regex_hits` on `(field, line)`."""
    found = identity.matches(["Welcome to Hill Country Animal Hospital"], LISTING, EMAIL)
    assert [(m.field, m.method) for m in found] == [
        ("name", "distinctive"), ("name", "substring"), ("slug", "substring")]


def test_matching_is_deterministic_and_ordered_by_line_then_field_then_method() -> None:
    """`matches` promises "ordered by line then field" and only line-monotonicity was asserted, so
    returning `found` unsorted stayed green (review Minor 13). The whole order is pinned here,
    because P7 turns this list into regions and a re-run must write the same `identity_matches`."""
    lines = ["Call (512) 555-0100 today", "HILL COUNTRY ANIMAL HOSPITAL"]
    once = identity.matches(lines, LISTING, EMAIL)
    assert once == identity.matches(lines, LISTING, EMAIL)
    assert [(m.line, m.field, m.method) for m in once] == [
        (0, "phone", "substring"),      # the number is INSIDE a sentence, so it is a substring too
        (0, "regex:phone", "regex"),    # "phone" < "regex:phone": the field is the second key
        (1, "name", "distinctive"),     # "distinctive" < "exact": the method is the third
        (1, "name", "exact"),
        (1, "slug", "exact"),
    ]


def test_the_four_thresholds_are_the_specs_own_numbers() -> None:
    """Spec C.5 step 3 states four numbers and the module states them again as named constants;
    nothing joined the two, so `FUZZY` could drift to 0.80 or 0.86 and `DISTINCTIVE` to 4 or 7 with
    the whole table green (review Minor 5). This is the repository's own two-way-pin idiom
    (`tests/census/test_design_shading_labels.py`), one tuple against the spec's four numbers."""
    assert (identity.MIN_SUBSTRING, identity.FUZZY, identity.TOKEN_SET, identity.DISTINCTIVE) \
        == (4, 0.85, 0.6, 5)


@pytest.mark.parametrize(("fragment", "informative"), [
    ("Hill Country", True),
    ("Animal Hospital", False),   # two tokens, both generic
    ("Cedar", False),             # one token
    ("Cypress", False),           # one token, and not generic at all
])
def test_informative_refuses_a_one_token_and_a_wholly_generic_fragment(fragment: str, informative: bool) -> None:
    """Both of `_informative`'s conditions, from both sides, on the fragment itself rather than
    through a match that several other rules could also explain."""
    assert identity._informative(identity.normalise(fragment)) is informative


def test_a_wholly_generic_practice_name_is_not_a_substring_of_a_longer_line() -> None:
    """`_compare`'s OTHER containment arm -- `term in line` (review Minor 2). Only the `line in
    term` arm was pinned, and this is the arm that protects a listing whose whole NAME is generic:
    "Animal Hospital" is contained in "Welcome to Animal Hospital", and without `_informative`
    guarding it too, every photograph carrying those two words on every listing would be masked."""
    generic: dict[str, Any] = {"name": "Animal Hospital"}
    assert identity.matches(["Welcome to Animal Hospital"], generic, None) == []


def test_a_one_token_line_never_reaches_the_token_set_method() -> None:
    """The two-token guard on `token_set` (re-review M-N), which fix round 1's report wrongly called
    unreachable. A term whose two tokens are the SAME word collapses to a one-element set, so a
    one-token line scores an overlap of 1.0 against it: Walla Walla is a real city in Washington
    with veterinary practices in it, and a sign truncated to "Walla" would be a `token_set` match at
    full confidence on every photograph of every practice there. The guard is what stops it, and
    nothing in the suite could see the guard removed."""
    assert identity.matches(["Walla"], {"city": "Walla Walla"}, None) == []


@pytest.mark.parametrize("word", sorted(identity.GENERIC))
def test_every_generic_word_is_generic_in_the_space_the_comparison_happens_in(word: str) -> None:
    """One row per word: two of the fourteen were pinned and twelve were free (review Minor 3).

    The assertion is behavioural and goes through `_informative`, because a word added to `GENERIC`
    in its human spelling filters NOTHING until `normalise` has folded it -- "animal" is "anlmal" in
    the space every comparison actually happens in, which is why `_GENERIC_N` exists. A fragment of
    this word beside another generic word must be uninformative; drop the word from the set and it
    becomes informative, and a substring match fires on every photograph carrying it."""
    assert not identity._informative(identity.normalise(f"{word} care"))


def test_the_near_miss_telephone_number_is_refused_by_both_floors_and_not_by_luck() -> None:
    """`(512) 555-9999` shares its area code and its exchange with the practice's own number, so it
    is the one MISS that comes close: six of the seven rows return [] because they share no token
    with any term at all (review Minor 3), which is not the reason the table's comment names. Both
    floors are doing work on this one, and neither is inert."""
    term = identity.identity_terms(LISTING, EMAIL)["phone"][0]
    line = identity.normalise("(512) 555-9999")
    assert identity._token_set(term, line) == 0.5 < identity.TOKEN_SET
    assert round(SequenceMatcher(None, term, line).ratio(), 3) == 0.667 < identity.FUZZY


def test_a_blank_line_never_matches_a_field_that_normalises_to_nothing() -> None:
    """`_compare`'s empty-side guard (review Minor 1). The `"   "` row of `MISSES` gave the guard
    its line coverage and not its behaviour: it supplies an empty LINE and never an empty TERM, and
    the exact-match collision the guard exists to stop needs both. A listing whose name is "???"
    normalises to the empty string, and without the guard a blank OCR line -- what an engine emits
    for a smudge -- is `name/exact/1.0` against it."""
    punctuation: dict[str, Any] = {"name": "???"}
    assert identity.identity_terms(punctuation, None)["name"] == [""]
    assert identity.matches(["   "], punctuation, None) == []


def test_a_two_token_fragment_below_the_length_floor_is_not_a_substring_match() -> None:
    """`MIN_SUBSTRING` is a floor UNDER `_informative`, not the "Rd inside Broadway" case the
    comment used to give: `_informative` refuses a one-token fragment before any length is tested,
    so that example was unreachable (review Minor 4). What the constant actually stops is a
    two-token fragment that is still only three characters -- "A B" standing in for "A B
    Veterinary" -- which is informative and is refused all the same, and reported by the weaker
    token_set method instead."""
    tiny: dict[str, Any] = {"name": "A B Veterinary"}
    assert identity._informative(identity.normalise("A B"))
    assert [m.method for m in identity.matches(["A B"], tiny, None) if m.field == "name"] \
        == ["token_set"]


def test_a_one_letter_abbreviation_is_never_an_abbreviation() -> None:
    """`_abbreviations` keeps nothing shorter than two letters, and both arms of that filter are a
    safety rule rather than tidiness. "Cypress Vet" has the initials CV, but its DISTINCTIVE
    initials are "C" alone -- one letter, which every capitalised sign in every photograph carries
    -- and a single-word name has nothing but that one letter, so it contributes no abbreviation at
    all. Neither arm is reachable through `HITS`, whose practice is four words long."""
    assert identity.identity_terms({"name": "Cypress Vet"}, None)["abbreviation"] == ["cv"]
    assert identity.identity_terms({"name": "Hillcountry"}, None)["abbreviation"] == []


def test_the_abbreviation_list_is_sorted_so_two_python_runs_agree() -> None:
    """`_abbreviations` builds its two arms in a set, and a set of strings iterates in
    PYTHONHASHSEED order: measured `['hc','hcah']` at seed 0 and `['hcah','hc']` at seeds 1 and
    12345 (review Minor 10). `matches()` only ever asks for membership, so nothing was wrong on the
    day; the list is sorted so that this assertion -- and any future one, and any privacy row built
    from it -- cannot flake between two CI runs of the same commit.

    SIX names, not one (re-review M-O): with the sort removed a two-element set comes out sorted on
    roughly half of all hash seeds, and at PYTHONHASHSEED=0 this fixture's own pair does, so a
    regression removing the sort passed on that seed. Each name is an independent coin-flip; six
    leave about one escape in sixty-four."""
    assert identity.identity_terms(LISTING, EMAIL)["abbreviation"] == ["hc", "hcah"]
    for name in ("Hill Country Animal Hospital", "Cypress Creek Veterinary Clinic",
                 "Round Rock Animal Care", "Bee Cave Pet Hospital",
                 "Oak Ridge Veterinary Center", "Cedar Park Animal Clinic"):
        abbreviations = identity._abbreviations(name)
        assert len(abbreviations) == 2, name
        assert abbreviations == sorted(abbreviations), name


def test_a_listing_with_no_identity_yet_matches_nothing_and_does_not_raise() -> None:
    """A draft before step 1: every field null. The pipeline still runs -- the regex classes are
    what protect that photograph -- and the matcher must not divide by zero on an empty term set."""
    empty: dict[str, Any] = dict.fromkeys(LISTING)
    assert [m for m in identity.matches(["HILL COUNTRY ANIMAL HOSPITAL"], empty, None)
            if m.method != "regex"] == []
