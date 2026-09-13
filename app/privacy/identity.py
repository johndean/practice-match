"""Matching a photograph's recognised text against this listing's own identity (spec C.5 step 3).

Stdlib only -- `difflib.SequenceMatcher` is the fuzzy method, so no dependency is added for it
(controller ruling 5). Nothing here is stored: the terms are read from the `listing` row at run
time, so a seller who corrects their practice name gets a re-run that matches the new one, and the
privacy row keeps only WHICH field matched WHICH line, by index, with a score.

Two directions have to be right at once. A matcher that fires on "Animal Hospital" blacks out every
photograph of every listing and teaches sellers to remove masks; one that only fires on the exact
registered name misses the sign, which is the whole point. Two rules hold the balance, and both are
about the same thing -- a fragment has to be SPECIFIC before it counts. The distinctive-token rule:
a name token of five characters or more, outside the generic set, is enough on its own. And
`_informative`, which every substring match must pass: at least two tokens, at least one of them
outside the generic set.

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
#: rather than a near-miss the fuzzy ratio has to rescue. Ordered longest-first so `rn` -> `m` runs
#: before the single-character pairs.
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

#: Each hit is an identifying region REGARDLESS of matching (spec C.5 step 2).
REGEX_CLASSES: dict[str, re.Pattern[str]] = {
    "phone": re.compile(r"(?<!\d)(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)"),
    "url": re.compile(r"\b(https?://\S+|www\.\S+|[\w-]+\.(com|net|org|vet|clinic|care|health|example)\b)", re.IGNORECASE),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    #: Two arms, and the second is not decoration: a suite number can stand with no street number
    #: in front of it. The specification's inline pattern (C.5 step 2) stated only the first and so
    #: would have missed "Suite 210"; A-IDP-7 corrects it there and folds both arms in here, so
    #: this module defines each class exactly once.
    "address": re.compile(
        r"(\b\d+\s+[\w'-]+(\s+[\w'-]+)*\s+(st|street|ave|avenue|rd|road|blvd|dr|drive|ln|lane|pkwy|parkway|hwy|highway)\b\.?"
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

#: Below this a substring is a coincidence ("Rd" inside "Broadway").
MIN_SUBSTRING = 4
#: `difflib` ratio at or above this is a match.
FUZZY = 0.85
#: Token-set overlap at or above this is a match, for lines of two tokens or more.
TOKEN_SET = 0.6
#: A name token this long, outside GENERIC, identifies on its own.
DISTINCTIVE = 5


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
    return [a for a in {full, distinctive} if len(a) >= 2]


def identity_terms(listing: Mapping[str, Any], email: str | None) -> dict[str, list[str]]:
    """The listing's own identity, normalised, by field.

    `tokens` is the distinctive-token pool: the name's own long words plus the long words of the
    seller's prose fields. `email_domain` is the part after the @ and never the part before it."""
    name = str(listing.get("name") or "")
    terms: dict[str, list[str]] = {
        field: [normalise(str(listing[field]))] if listing.get(field) else []
        for field in ("name", "street", "city", "state", "zip", "phone", "slug")
    }
    terms["email_domain"] = [normalise(email.split("@", 1)[1])] if email and "@" in email else []
    terms["abbreviation"] = _abbreviations(name)
    prose = " ".join(str(listing.get(f) or "") for f in ("facility", "services", "hours"))
    pool = {t for t in normalise(f"{name} {prose}").split() if len(t) >= DISTINCTIVE and t not in _GENERIC_N}
    terms["tokens"] = sorted(pool)
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
            if field in ("tokens", "abbreviation"):
                continue
            for term in values:
                hit = _compare(field, term, line)
                if hit is not None:
                    found.append(hit._replace(line=index))
                    break
        words = set(line.split())
        for token in terms.get("tokens", ()):
            if token in words:
                found.append(Match("name", index, "distinctive", 0.8))
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
    """The lines as one string, and each line's `[start, end)` span within it."""
    spans: list[tuple[int, int]] = []
    at = 0
    for line in lines:
        spans.append((at, at + len(line)))
        at += len(line) + len(JOIN)
    return JOIN.join(lines), spans


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
