"""Matching a photograph's recognised text against this listing's own identity (spec C.5 step 3).

Stdlib only -- `difflib.SequenceMatcher` is the fuzzy method, so no dependency is added for it
(controller ruling 5). Nothing here is stored: the terms are read from the `listing` row at run
time, so a seller who corrects their practice name gets a re-run that matches the new one, and the
privacy row keeps only WHICH field matched WHICH line, by index, with a score.

Two directions have to be right at once. A matcher that fires on "Animal Hospital" blacks out every
photograph of every listing and teaches sellers to remove masks; one that only fires on the exact
registered name misses the sign, which is the whole point. Two rules hold the balance, and both are
about the same thing -- a fragment has to be SPECIFIC before it counts. The distinctive-token rule:
a token of five characters or more, outside the generic set, is enough on its own -- from the NAME
it is reported as `name` and from the seller's prose as `prose`, because the privacy row names a
column to whoever reads it. And `_informative`, which every substring match must pass: at least two
tokens, at least one of them outside the generic set.

**The generic set is compared AFTER normalisation, and that is load-bearing.** `normalise` folds the
scene-text confusions on both sides, so "animal" becomes "anlmal" and "hospital" becomes "hospltal";
a generic set of un-normalised words would therefore match none of the tokens it is meant to filter,
`_informative` and the distinctive pool would both let them through, and the matcher would black out
a region on every photograph carrying the words "animal hospital". `normalise` is defined first for
that reason and `_GENERIC_N` is folded at import."""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher
from typing import Any, NamedTuple

#: Applied to BOTH sides before comparison, so "H0SPITAL" and "HOSPITAL" become the same string
#: rather than a near-miss the fuzzy ratio has to rescue. Written longest-first for a reader; the
#: ORDER is NOT load-bearing, and the comment used to claim it was (review I-2). No pair's OUTPUT
#: character (`m w o l s b z`) is any pair's INPUT (`rn vv 0 1 i 5 8 2`), so the map reaches one
#: fixed point whatever order it is applied in -- which is exactly what makes folding both sides of
#: a comparison safe. `tests/privacy/test_identity.py` pins that property, and each of the eight
#: pairs has one row of `HITS` that goes red when the pair is deleted.
SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("rn", "m"), ("vv", "w"), ("0", "o"), ("1", "l"), ("i", "l"), ("5", "s"), ("8", "b"), ("2", "z"),
)


def normalise(text: str) -> str:
    """Casefold, punctuation to spaces, whitespace collapsed, OCR confusions folded."""
    folded = re.sub(r"[^\w\s]", " ", text.casefold())
    collapsed = " ".join(folded.split())
    for wrong, right in SUBSTITUTIONS:
        collapsed = collapsed.replace(wrong, right)
    return collapsed


#: Words that identify no practice, as written. Used nowhere directly -- every comparison is against
#: `_GENERIC_N` below -- but kept in this spelling because it is the human-readable list, and a
#: reader adding a word to it should not have to know what the substitution map will do to it.
GENERIC = frozenset({"animal", "hospital", "veterinary", "vet", "clinic", "pet", "care", "center",
                     "centre", "of", "the", "and", "for", "dvm"})

#: The same words in the space every comparison actually happens in: "animal" -> "anlmal",
#: "hospital" -> "hospltal", "veterinary" -> "veterlnary", "clinic" -> "cllnlc". Folded once, at
#: import, because a set folded per call would be the same work in a loop.
_GENERIC_N = frozenset(normalise(word) for word in GENERIC)

#: The bare-domain TLDs `url` recognises with no scheme and no `www.` in front of them. Spec C.5
#: step 2 asks for "a maintained TLD list" and this tuple IS that seam -- a TLD is added here and
#: nowhere else, and `tests/privacy/test_identity.py` walks every entry of it, so an addition is
#: proved to fire rather than merely declared. `.co`, `.us`, `.io`, `.info` and `.pet` were missing
#: and a practice's bare domain on one of them was no region at all (review Minor 7). `example` is
#: deliberately NOT here: it is RFC 2606's documentation TLD, belongs to no practice, and a
#: production class that recognised it would be a class tuned to this repository's own fixtures.
URL_TLDS: tuple[str, ...] = ("com", "net", "org", "co", "us", "io", "info", "pet", "vet",
                             "clinic", "care", "health")

#: Interpolated longest-first, so a shorter entry cannot be tried where a longer one that starts
#: with the same letters is meant (`co` before `com`).
_TLDS = "|".join(sorted(URL_TLDS, key=len, reverse=True))

#: Each hit is an identifying region REGARDLESS of matching (spec C.5 step 2).
REGEX_CLASSES: dict[str, re.Pattern[str]] = {
    "phone": re.compile(r"(?<!\d)(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"),
    "url": re.compile(rf"\b(https?://\S+|www\.\S+|[\w-]+\.({_TLDS})\b)", re.IGNORECASE),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    #: Two arms, and the second is not decoration: a suite number can stand with no street number
    #: in front of it. The specification's inline pattern (C.5 step 2) stated only the first and so
    #: would have missed "Suite 210"; A-IDP-7 corrects it there and folds both arms in here, so
    #: this module defines each class exactly once.
    #:
    #: `dr` is split out of the street-type list and carries its own `(?!\s+[\w'-])` (review
    #: Minor 8): "Dr" is the title as often as it is Drive, any digit on the line can stand in as
    #: the house number, and so "Open 7 days with Dr Jones" and "24/7 Emergency Dr Smith" were both
    #: `regex:address` -- a mask over every interior sign that names a veterinarian beside a number,
    #: which is how a seller learns to remove masks. A street suffix ENDS its address ("... Creek
    #: Dr", "... Creek Dr, Cedar Park"); a title is followed by a name. The cost is measured and
    #: recorded rather than hidden: "1204 Cypress Creek Dr Cedar Park TX", with no comma, is no
    #: longer an address region -- for the listing's own address the `street` term still matches the
    #: line, and `drive`, `rd` and the other eleven suffixes are untouched.
    "address": re.compile(
        r"(\b\d+\s+[\w'-]+(\s+[\w'-]+)*\s+(?:"
        r"(?:st|street|ave|avenue|rd|road|blvd|drive|ln|lane|pkwy|parkway|hwy|highway)\b\.?"
        r"|dr\b\.?(?!\s+[\w'-]))"
        r"|\b(suite|ste)\s*\.?\s*\w+\b)", re.IGNORECASE),
    #: A number worn as signage, alone on its own line: "4140" above a door. John's ruling of
    #: 2026-09-10 (A-IDP-7) -- an invented street number is part of the invented identity, so it
    #: is redacted under NOT_SHOW like the name. WHOLE LINE, two to six digits: "EST. 2017",
    #: "EXAM ROOM 1" and "24/7" carry other tokens and are not premises numbers, so an interior
    #: is not blanketed; where a number shares a line with the practice's own name the identity
    #: match already makes the whole line one region (spec C.5 step 5).
    "premises_number": re.compile(r"\A\s*\d{2,6}\s*\Z"),
    "handle": re.compile(r"(?<!\w)@\w{3,}"),
    "zip": re.compile(r"(?<!\d)\d{5}(?!\d)"),
}

#: A floor UNDER `_informative`, and not a rule of its own: `_informative` already refuses a
#: one-token fragment, so the "Rd inside Broadway" case this comment used to give could never reach
#: the length test at all (review Minor 4). What the constant stops is a two-token fragment that is
#: still only three characters -- "A B" standing in for "A B Veterinary". Spec C.5's "min 4 chars".
MIN_SUBSTRING = 4
#: `difflib` ratio at or above this is a match. Spec C.5 step 3's own number.
FUZZY = 0.85
#: Token-set overlap at or above this is a match, for lines of two tokens or more. Spec C.5's own.
TOKEN_SET = 0.6
#: A token this long, outside GENERIC, identifies on its own. Spec C.5's own number. All four are
#: pinned against the specification's four numbers by one test, because nothing else joined them
#: and FUZZY could drift to 0.80 or 0.86 with the whole table green (review Minor 5).
DISTINCTIVE = 5

#: The two distinctive-token pools, and the `Match.field` each is reported under. A long word out of
#: the seller's prose is not the practice's NAME: the privacy row's `identity_matches` names a
#: COLUMN to whoever reads it, and the line "Dentistry" -- from `services` -- was recorded as `name`
#: (review Minor 9). A word in BOTH pools belongs to the name, which is why `prose` is built as the
#: difference and not the union.
TOKEN_POOLS: tuple[tuple[str, str], ...] = (("tokens", "name"), ("prose", "prose"))

#: The keys of `identity_terms` that are NOT whole-string terms: the two pools above and the
#: abbreviation list, each of which has its own pass in `match_lines`.
_NOT_TERMS = frozenset({"tokens", "prose", "abbreviation"})


class Match(NamedTuple):
    field: str
    line: int
    method: str
    score: float


def _informative(fragment: str) -> bool:
    """Whether a normalised fragment is specific enough to be a substring match on its own.

    Two conditions, and a review found the matcher wrong on both. At least TWO tokens, or "Cedar"
    -- one token of the two-token city "Cedar Park" -- is a substring match on every photograph of
    every practice in Cedar Park. And at least one token outside the generic veterinary vocabulary,
    or "Animal Hospital" is a substring of "Hill Country Animal Hospital" and every photograph of
    every listing goes dark. `MISSES` in `tests/privacy/test_identity.py` has a row for each."""
    tokens = fragment.split()
    return len(tokens) >= 2 and any(token not in _GENERIC_N for token in tokens)


def _abbreviations(name: str) -> list[str]:
    words = [w for w in normalise(name).split() if w]
    if not words:
        return []
    full = "".join(w[0] for w in words)
    distinctive = "".join(w[0] for w in words if w not in _GENERIC_N)
    # `sorted`, not set order: a set of strings iterates in PYTHONHASHSEED order, and this list came
    # back `['hc','hcah']` at seed 0 and `['hcah','hc']` at seeds 1 and 12345 (review Minor 10).
    # `match_lines` only ever asks it for membership, so nothing was wrong on the day; an assertion
    # on it, or a privacy row built from it, would have flaked between two runs of one commit.
    return sorted(a for a in {full, distinctive} if len(a) >= 2)


def _pool(text: str) -> set[str]:
    """The distinctive tokens of a string: long enough to identify on their own, and outside the
    generic veterinary vocabulary."""
    return {t for t in normalise(text).split() if len(t) >= DISTINCTIVE and t not in _GENERIC_N}


def identity_terms(listing: Mapping[str, Any], email: str | None) -> dict[str, list[str]]:
    """The listing's own identity, normalised, by field.

    `tokens` is the NAME's own distinctive-token pool and `prose` is the seller's free-text one,
    kept apart so a match can say which of the two it came from (review Minor 9).
    `email_domain` is the part after the @ and never the part before it."""
    name = str(listing.get("name") or "")
    terms: dict[str, list[str]] = {
        field: [normalise(str(listing[field]))] if listing.get(field) else []
        for field in ("name", "street", "city", "state", "zip", "phone", "slug")
    }
    terms["email_domain"] = [normalise(email.split("@", 1)[1])] if email and "@" in email else []
    terms["abbreviation"] = _abbreviations(name)
    prose = " ".join(str(listing.get(f) or "") for f in ("facility", "services", "hours"))
    own = _pool(name)
    terms["tokens"] = sorted(own)
    terms["prose"] = sorted(_pool(prose) - own)
    return terms


def _token_set(a: str, b: str) -> float:
    left, right = set(a.split()), set(b.split())
    return len(left & right) / len(left | right) if left and right else 0.0


def _compare(field: str, term: str, line: str) -> Match | None:
    """The methods in order; the FIRST that fires wins, so a match is reported by the strongest
    method that explains it rather than by all of them at once."""
    if not term or not line:
        return None
    if term == line:
        return Match(field, 0, "exact", 1.0)
    # Containment either way -- a sign that carries the whole name inside a sentence, and a name
    # truncated by the sign's own frame -- but only where the CONTAINED fragment is informative.
    if len(term) >= MIN_SUBSTRING and term in line and _informative(term):
        return Match(field, 0, "substring", 0.9)
    if len(line) >= MIN_SUBSTRING and line in term and _informative(line):
        return Match(field, 0, "substring", 0.9)
    if len(line.split()) >= 2:
        overlap = _token_set(term, line)
        if overlap >= TOKEN_SET:
            return Match(field, 0, "token_set", round(overlap, 3))
    ratio = SequenceMatcher(None, term, line).ratio()
    if ratio >= FUZZY:
        return Match(field, 0, "fuzzy", round(ratio, 3))
    return None


def match_lines(lines: Sequence[str], terms: Mapping[str, list[str]]) -> list[Match]:
    found: list[Match] = []
    for index, raw in enumerate(lines):
        line = normalise(raw)
        for field, values in terms.items():
            if field in _NOT_TERMS:
                continue
            for term in values:
                hit = _compare(field, term, line)
                if hit is not None:
                    found.append(hit._replace(line=index))
                    break
        words = set(line.split())
        for pool, as_field in TOKEN_POOLS:
            for token in terms.get(pool, ()):
                if token in words:
                    found.append(Match(as_field, index, "distinctive", 0.8))
                    break
        upper = raw.strip()
        # One `if` and not two: the repository's ruff set carries SIM102, and `and` is the same
        # short-circuit the nested form was -- the cheap shape test still runs before `normalise`.
        if (2 <= len(upper) <= 6 and upper.isalpha() and upper.isupper()
                and normalise(upper) in terms.get("abbreviation", ())):
            found.append(Match("name", index, "abbreviation", 0.75))
    return found


#: What the joined pass puts between two lines. One space, so a sign that wrapped reads as one
#: string; never a newline, because none of the classes is written with `re.M`.
JOIN = " "


def _spans(lines: Sequence[str]) -> tuple[str, list[tuple[int, int]]]:
    """The lines as one string, and each line's `[start, end)` span within it.

    Every line is STRIPPED before it is joined, and a blank one contributes no separator at all
    (review I-1). `app/privacy/ocr.py` takes the engine's `text` verbatim -- no strip, no filter --
    so a wrapped sign arrives as `["(512) ", "555-0100"]` as readily as perfectly trimmed, and one
    character of padding made the join `"(512)  555-0100"`: `phone`'s separator class is a SINGLE
    optional character, so it could not cross the double space and the number was a region on
    NEITHER line. That is under-redaction, in the exact case this pass exists for.

    A blank line takes the impossible span `(-1, -1)`, so the index of a span is still the index of
    its line -- `regex_hits` attributes by position -- while no match can ever be attributed to a
    line that holds no text and therefore no pixels to fill."""
    spans: list[tuple[int, int]] = []
    parts: list[str] = []
    at = 0
    for line in lines:
        text = line.strip()
        if not text:
            spans.append((-1, -1))
            continue
        if parts:
            at += len(JOIN)
        parts.append(text)
        spans.append((at, at + len(text)))
        at += len(text)
    return JOIN.join(parts), spans


def regex_hits(lines: Sequence[str]) -> list[Match]:
    """Every class that fires on a line, plus every class that fires only on the JOINED text.

    Spec C.5 step 2 runs the classes "over every line and over the joined text", and the second half
    is not decoration: scene text wraps, so "(512)" on one line of a sign and "555-0100" on the next
    is a telephone number that no per-line pass can ever see. A joined hit is attributed to EVERY
    line whose span the match touches, so the aggregator covers both halves of the wrap rather than
    one rectangle spanning the gap between them, and `(field, line)` is deduplicated so a match the
    per-line pass already found is not recorded twice."""
    found = [Match(f"regex:{cls}", index, "regex", 1.0)
             for index, line in enumerate(lines)
             for cls, pattern in REGEX_CLASSES.items() if pattern.search(line)]
    if len(lines) < 2:
        return found
    joined, spans = _spans(lines)
    seen = {(m.field, m.line) for m in found}
    for cls, pattern in REGEX_CLASSES.items():
        for match in pattern.finditer(joined):
            for index, (start, end) in enumerate(spans):
                if start < match.end() and match.start() < end and (f"regex:{cls}", index) not in seen:
                    seen.add((f"regex:{cls}", index))
                    found.append(Match(f"regex:{cls}", index, "regex", 1.0))
    return found


def matches(lines: Sequence[str], listing: Mapping[str, Any], email: str | None) -> list[Match]:
    """Every match, ordered by line then field -- deterministic, so a re-run of the same inputs
    writes the same `identity_matches` and the same regions (spec C.5 step 5)."""
    found = match_lines(lines, identity_terms(listing, email)) + list(regex_hits(lines))
    return sorted(found, key=lambda m: (m.line, m.field, m.method))
