"""Identity matching (spec 2026-09-09 C.5 step 3; directive 4 step 3).

The directive asks for exact, case-insensitive, punctuation- and whitespace-normalised, OCR-error-
tolerant, partial and abbreviation matching. Every row of the table below is one of those, and the
OCR-error rows are real substitutions a scene-text engine makes on signage: a serif I read as a 1, a
zero read as an O, an `rn` pair read as an `m`."""
from __future__ import annotations

from typing import Any

import pytest

from app.privacy import identity

LISTING: dict[str, Any] = {
    "name": "Hill Country Animal Hospital",
    "street": "1204 Cypress Creek Rd",
    "city": "Cedar Park",
    "state": "TX",
    "zip": "78613",
    "phone": "(512) 555-0100",
    "slug": "hill-country-animal-hospital",
    "facility": "Two-storey brick building on Cypress Creek",
    "services": "Dentistry, surgery, boarding",
    "hours": "Mon-Fri 8-6",
}
EMAIL = "practice.manager@hillcountryvet.example"

# (the OCR line, the field it must match, the method it must match by)
#
# The METHOD column is derived, not chosen: `_compare` returns the FIRST method that fires, in the
# order exact -> substring -> token_set -> fuzzy, so each row records which of them actually
# explains that line under the normalisation below. Three rows are worth reading twice.
# "HILL COUNTRY ANIMAL HOSP" is a prefix of the normalised name, so `substring` fires before
# `token_set` ever runs; "ANIIVIAL" scores a token-set overlap of exactly 3/5 = 0.6, which is
# `>= TOKEN_SET`, so it is a token_set and not a fuzzy; and `fuzzy` is only ever reached by a line
# of two or more tokens whose overlap is BELOW 0.6, which is what "Cedar Parh" is for.
HITS = (
    ("Hill Country Animal Hospital", "name", "exact"),
    ("HILL COUNTRY ANIMAL HOSPITAL", "name", "exact"),                 # case
    ("Hill Country Animal Hospital.", "name", "exact"),                # punctuation
    ("Hill  Country   Animal Hospital", "name", "exact"),              # whitespace
    ("Welcome to Hill Country Animal Hospital", "name", "substring"),  # partial
    ("HILL C0UNTRY ANIMAL H0SPITAL", "name", "exact"),                 # OCR: 0 for O
    ("HlLL COUNTRY ANIMAL HOSPITAL", "name", "exact"),                 # OCR: l for I
    ("HILL COUNTRY ANIIVIAL HOSPITAL", "name", "token_set"),           # OCR: IVI for M -- 3/5 = 0.60
    ("HILL COUNTRY ANIMAL HOSP", "name", "substring"),                 # truncated by the sign's frame
    ("Cedar Parh", "city", "fuzzy"),                                   # OCR: h for k -- overlap 0.33, ratio 0.90
    ("Hill Country", "name", "distinctive"),                           # the sign's top line alone
    ("HCAH", "name", "abbreviation"),
    ("1204 Cypress Creek Rd", "street", "exact"),
    ("Cedar Park", "city", "exact"),
    ("78613", "zip", "exact"),
    ("(512) 555-0100", "phone", "exact"),
    ("512.555.0100", "phone", "exact"),                                # punctuation again
    ("hillcountryvet.example", "email_domain", "exact"),
    ("hill-country-animal-hospital", "slug", "exact"),
)

# Lines that must NOT match anything: the generic words a veterinary sign carries everywhere, and a
# number that is not this practice's. A matcher that fires on "Animal Hospital" would black out
# every photograph of every listing and teach sellers to remove masks. Both rules `_informative`
# enforces have a row here, because both were found by a review reading the matcher against this
# very table: "Animal Hospital" is two tokens that are BOTH generic, and "Cedar" is a single token
# of a two-token city.
#
# The last two rows were added by the coverage gate rather than chosen (the brief's Step 3: where a
# branch is not reached, ADD THE ROW). "OPEN" is short, alphabetic and upper case, so it reaches the
# abbreviation test and FAILS it -- without it nothing ever asked whether a line that merely LOOKS
# like initials is rejected, and the matcher would have passed the table while blacking out every
# four-letter sign. (Its branch is now a short-circuit term of one `if` rather than a nested one --
# ruff's SIM102 -- so coverage no longer NAMES it; the row stays because it is the only thing that
# asks the question.) A blank line is what an OCR engine emits for a smudge or a shadow, and it is
# the only input that reaches `_compare`'s empty-string guard: every term would otherwise be
# compared against "" and `SequenceMatcher` would score two empty strings 1.0.
MISSES = (
    "Animal Hospital",
    "VETERINARY CLINIC",
    "Open 7 days",
    "Cedar",                       # one token of "Cedar Park": a substring, and not an identity
    "(512) 555-9999",
    "OPEN",                        # short, alphabetic, upper case -- and not this practice's initials
    "   ",                         # a blank line: the guard in `_compare` that refuses an empty side
)


@pytest.mark.parametrize(("line", "field", "method"), HITS)
def test_every_contracted_match_is_found_by_its_contracted_method(line: str, field: str, method: str) -> None:
    found = identity.matches([line], LISTING, EMAIL)
    assert [(m.field, m.method) for m in found if m.field == field] != [], found
    assert any(m.field == field and m.method == method for m in found), found
    assert all(0.0 <= m.score <= 1.0 and m.line == 0 for m in found)


@pytest.mark.parametrize("line", MISSES)
def test_a_generic_or_foreign_line_matches_no_identity_field(line: str) -> None:
    assert [m for m in identity.matches([line], LISTING, EMAIL) if m.method != "regex"] == []


@pytest.mark.parametrize(("line", "cls"), [
    ("Call (512) 555-0100 today", "phone"),
    ("visit hillcountryvet.example", "url"),
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
    listing or any other, which is exactly why the identity matcher can never reach it."""
    other: dict[str, Any] = {"name": "Somewhere Else Veterinary", "city": "Dallas", "zip": "75001"}
    assert any(m.field == f"regex:{cls}" and m.method == "regex"
               for m in identity.matches([line], other, None))


@pytest.mark.parametrize("line", ["EST. 2017", "EXAM ROOM 1", "24/7", "Open 7 days", "1"])
def test_a_line_that_is_not_only_a_number_is_not_a_premises_number(line: str) -> None:
    """`premises_number` is deliberately WHOLE-LINE and two to six digits (A-IDP-7), so an interior
    is not blanketed: an established-in year, a room number and an opening-hours pill all carry
    other tokens, and a single digit is too short. Where a number DOES share a line with the
    practice's own name, the identity match already makes that whole line one region."""
    assert [m for m in identity.matches([line], LISTING, EMAIL)
            if m.field == "regex:premises_number"] == []


def test_a_number_split_across_two_lines_is_still_a_hit_on_both_of_them() -> None:
    """Spec C.5 step 2 runs the regex classes "over every line and over the joined text". Scene text
    wraps: an area code on one line of a sign and the rest on the next is a telephone number no
    per-line pass can see, and the aggregator needs BOTH lines so the fill covers both halves rather
    than one rectangle spanning the gap between them."""
    found = identity.matches(["(512)", "555-0100"], LISTING, EMAIL)
    assert sorted(m.line for m in found if m.field == "regex:phone") == [0, 1]
    # and no line matched it on its own -- neither half is ten digits
    for half in ("(512)", "555-0100"):
        assert [m for m in identity.matches([half], LISTING, EMAIL) if m.field == "regex:phone"] == []


def test_a_joined_hit_is_recorded_once_per_line_and_not_twice() -> None:
    """The per-line pass and the joined pass see the same match on a single-line input; the record
    carries one entry, because `identity_matches` indexes into `ocr.lines` and a duplicate would
    make the same region twice."""
    found = [m for m in identity.matches(["Call (512) 555-0100 today"], LISTING, EMAIL)
             if m.field == "regex:phone"]
    assert len(found) == 1


def test_only_the_email_domain_is_ever_read() -> None:
    """Data minimisation (spec C.5 step 3): the part before the @ is a person's name as often as
    not, and no photograph of a building contains it.

    The domain is stored NORMALISED, like every other term -- `hillcountryvet.example` folds to
    `hlllcountryvet example` under the substitution map -- so the assertion is against that
    spelling. Asserting the raw address would fail against a correct matcher, which is the sort of
    row that gets a working rule "fixed"."""
    terms = identity.identity_terms(LISTING, EMAIL)
    assert terms["email_domain"] == [identity.normalise("hillcountryvet.example")]
    assert "manager" not in str(terms) and identity.normalise("practice") not in str(terms)


def test_the_seller_prose_fields_contribute_tokens_and_never_whole_string_matches() -> None:
    """`facility`, `services` and `hours` are free text: matching a whole sentence would fire on
    nothing, and matching every word in them would fire on everything. Distinctive tokens only."""
    terms = identity.identity_terms(LISTING, EMAIL)
    assert "Two-storey brick building on Cypress Creek" not in terms["name"]
    assert any("cypress" in t for t in terms["tokens"])
    assert not any(t in ("mon", "fri", "8", "6") for t in terms["tokens"])


def test_a_one_letter_abbreviation_is_never_an_abbreviation() -> None:
    """`_abbreviations` keeps nothing shorter than two letters, and both arms of that filter are a
    safety rule rather than tidiness. "Cypress Vet" has the initials CV, but its DISTINCTIVE
    initials are "C" alone -- one letter, which every capitalised sign in every photograph carries
    -- and a single-word name has nothing but that one letter, so it contributes no abbreviation at
    all. Neither arm is reachable through `HITS`, whose practice is four words long."""
    assert identity.identity_terms({"name": "Cypress Vet"}, None)["abbreviation"] == ["cv"]
    assert identity.identity_terms({"name": "Hillcountry"}, None)["abbreviation"] == []


def test_matching_is_deterministic_and_ordered_by_line_then_field() -> None:
    lines = ["HILL COUNTRY ANIMAL HOSPITAL", "(512) 555-0100"]
    once = identity.matches(lines, LISTING, EMAIL)
    assert once == identity.matches(lines, LISTING, EMAIL)
    assert [m.line for m in once] == sorted(m.line for m in once)


def test_a_listing_with_no_identity_yet_matches_nothing_and_does_not_raise() -> None:
    """A draft before step 1: every field null. The pipeline still runs -- the regex classes are
    what protect that photograph -- and the matcher must not divide by zero on an empty term set."""
    empty: dict[str, Any] = dict.fromkeys(LISTING)
    assert [m for m in identity.matches(["HILL COUNTRY ANIMAL HOSPITAL"], empty, None)
            if m.method != "regex"] == []
