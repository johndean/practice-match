"""Task CI-TIMING. Real wall-clock budget tests against a live Postgres/Redis and a real ASGI app
— constant-time auth checks (a network-timing side channel) and p95 latency gates — failed on a
loaded 20-stack developer machine while passing 5/5 in isolation: scheduled beside CPU-heavy tests
(Argon2id hashing, media encoding, Census geometry), they measured the machine, not the code. The
budgets themselves are correct and untouched by this task — what moves is WHEN they run:
`@pytest.mark.timing` (registered in `pyproject.toml`) pulls them out of the normal run and into a
second, serial, LAST step of the gate (`-m timing -p no:randomly`, coverage appended onto the
first step's — see CLAUDE.md's Common operations and `.github/workflows/quality.yml`).

This module is the RED-first proof that the marker is actually on every test that needs it, and
the mechanism a NEW timing-sensitive test is caught by if its author forgets the marker.

THE PREDICATE (`reads_the_clock`, below) is structural, not a hand-typed list of names — a
hand-typed list could recite the past but could not "catch a new timing test": a test reads the
wall clock if its own source contains `time.perf_counter()`, or if it calls a plain
(module-level-resolvable) helper that does, recursively — the one hop this project's own shape
needs, for `test_p95_within_budget`, whose `measure()` closure calls the shared `_samples()`
helper rather than reading the clock inline. Every OTHER budgeted test in `test_api_latency.py`
reads the clock directly inside its own inline `measure()` closure, so the recursion is exercised
by exactly the one case that needs it — not a speculative allowance.

Applied across the whole suite, the predicate finds **fourteen** tests:

  * the three constant-time auth checks the round 0 brief named plus a fourth, structurally
    identical sibling (`test_signin_failures_are_generic_for_wrong_unknown_suspended_and_revoked`,
    a 5x looser tolerance — 100 ms of pairwise median spread against the trio's 20 ms);
  * `test_cold_principal_cache_me_p95_within_budget` plus seven more in `test_api_latency.py` that
    assert through the same `gate_p95` helper (that function's own docstring: "The p95 gate every
    latency test asserts through") — `test_p95_within_budget` and its six budgeted paths,
    `test_anonymous_well_formed_bearer_p95_within_budget`, `test_signin_p95_under_300ms`,
    `test_signup_p95_within_budget`, `test_interest_stored_path_p95_within_budget`,
    `test_listings_p95_within_budget`, `test_market_api_p95_within_budget`;
  * two more elsewhere: `tests/test_db.py::test_check_db_and_check_redis_time_out_against_a_
    black_hole` (a literal `budget` variable) and `tests/auth/test_passwords.py::
    test_argon2id_parameters_hash_verify_rehash_and_cost` (a single Argon2id verify under 250 ms).

**Fix round 1 correction.** Round 0's own report said "thirteen," miscounting its own
`NOT_YET_SERIALISED` set by one (ten entries were declared, not nine, and 4 + 10 = 14, not 13) —
found on re-count during the fix-round review, not by this predicate, which was right both times.
Round 0 marked only the first four `@pytest.mark.timing` and left the other ten declared
`NOT_YET_SERIALISED` as an accepted gap; that gap turned out to be LIVE rather than theoretical —
three of the ten failed in round 0's own step-1 run the same day — so round 1's ruling folds all
fourteen into `MARKED` and `NOT_YET_SERIALISED` becomes the **empty set**, checked in both
directions: `test_every_timing_budget_test_is_accounted_for` (below) still asserts nothing the
predicate matches is undeclared and nothing declared has stopped matching — with
`NOT_YET_SERIALISED` empty this collapses to "declared == candidates == MARKED, exactly" — and
`test_the_not_yet_serialised_gap_stays_closed` pins the set itself at `set()` so the gap cannot
reopen silently, one entry at a time, without a visible diff to this file. A genuinely NEW timing
test is caught the same way it always was: it satisfies the predicate, it is declared nowhere, and
`test_every_timing_budget_test_is_accounted_for` fails, by name, until a human marks it.

Proved RED again for fix round 1, the same way as round 0: temporarily left
`test_argon2id_parameters_hash_verify_rehash_and_cost` unmarked and reran —
`test_every_timing_budget_test_is_accounted_for` failed, naming it as a candidate declared
nowhere (`NOT_YET_SERIALISED` no longer exists as a place to park it); restored, reran, green.

**Fix round 2 correction.** Both rounds above scanned only `MODULES` — a hand-picked 4-tuple
(`test_auth`, `test_api_latency`, `test_db`, `test_passwords`) — so the opening paragraph's own
claim, "applied across the whole suite", was false: a `time.perf_counter()` test added to any OTHER
module (the other eighty in `tests/`) would never be discovered, marked or not. Proved directly:
a throwaway module, `tests/_tmp_fifth_module_test.py`, with one unmarked function reading the clock
(`test_a_new_unmarked_timing_probe`) was added and `test_every_timing_budget_test_is_accounted_for`
still passed — `3 passed`, silently blind to it — under the old `MODULES` tuple.

`_discover_test_modules` (below) replaces `MODULES`: it walks `tests/` itself and imports every
file pytest's own default `python_files` patterns would collect as a test module (`test_*.py` and
`*_test.py` — matched, not assumed; `pyproject.toml` sets no override), so a FIFTH module — a new
file in an existing package, or a whole new subpackage — is found the moment it exists, with no
line to add here. Re-ran the same throwaway module against the walk:
`test_every_timing_budget_test_is_accounted_for` now FAILED, naming
`tests._tmp_fifth_module_test::test_a_new_unmarked_timing_probe` as a new, undeclared candidate —
proving the fix catches exactly what the old tuple missed. The throwaway module is then deleted
(it does not ship); `_discover_test_modules` also happens to pick up `tests/e2e/api_under_test.py`
(matches `*_test.py`) and every other real `test_*.py` file in the tree, none of which changes the
candidate set — `api_under_test.py` is production-shaped code with no `test_`-prefixed function in
it (pytest itself collects it as a module and finds zero test items, checked directly), and every
other file was already being imported by every full-suite run regardless.
"""
import ast
import fnmatch
import importlib
import inspect
import textwrap
from pathlib import Path

from tests import test_db
from tests.api import test_auth
from tests.auth import test_passwords
from tests.perf import test_api_latency

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"

# pytest's own default `python_files` (pyproject.toml's `[tool.pytest.ini_options]` sets no
# override — read directly above, not assumed). Matched here so the walk finds exactly what
# pytest itself would collect as a test module, not an arbitrary subset of it.
_PYTEST_DEFAULT_TEST_FILE_GLOBS = ("test_*.py", "*_test.py")


def _is_a_pytest_test_module(filename: str) -> bool:
    return any(fnmatch.fnmatch(filename, pattern) for pattern in _PYTEST_DEFAULT_TEST_FILE_GLOBS)


def _discover_test_modules() -> list[object]:
    """Every module under `tests/` pytest's own default collection rules would treat as a test
    module — walked from the directory, not a hand-picked list of imports, so a new module is
    found the moment it exists. `tests/` and every sub-package under it already declare
    `__init__.py` (checked directly), so each discovered file has a valid dotted import path."""
    modules = []
    for path in sorted(TESTS_DIR.rglob("*.py")):
        if not _is_a_pytest_test_module(path.name):
            continue
        dotted = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        modules.append(importlib.import_module(dotted))
    return modules

# All fourteen tests `reads_the_clock` matches, `@pytest.mark.timing`, moved to the gate's serial,
# last step (fix round 1 — round 0 marked only the first four here and named the other ten
# `NOT_YET_SERIALISED`; see the module docstring for why round 1 closes that gap).
MARKED = {
    (test_auth, "test_signup_does_the_same_work_for_a_new_and_an_existing_address"),
    (test_auth, "test_the_re_issue_branch_answers_in_the_same_time_as_the_account_exists_branch"),
    (test_auth, "test_a_new_address_and_an_existing_unverified_one_answer_in_the_same_time"),
    (test_auth, "test_signin_failures_are_generic_for_wrong_unknown_suspended_and_revoked"),
    (test_api_latency, "test_cold_principal_cache_me_p95_within_budget"),
    (test_api_latency, "test_p95_within_budget"),
    (test_api_latency, "test_anonymous_well_formed_bearer_p95_within_budget"),
    (test_api_latency, "test_signin_p95_under_300ms"),
    (test_api_latency, "test_signup_p95_within_budget"),
    (test_api_latency, "test_interest_stored_path_p95_within_budget"),
    (test_api_latency, "test_listings_p95_within_budget"),
    (test_api_latency, "test_market_api_p95_within_budget"),
    (test_db, "test_check_db_and_check_redis_time_out_against_a_black_hole"),
    (test_passwords, "test_argon2id_parameters_hash_verify_rehash_and_cost"),
}

# Fix round 1 (John's ruling): the class is closed, not partially deferred. Kept declared — rather
# than deleted along with the mechanism — so a future exemption is a visible, deliberate diff to
# this file and this constant, never a silent omission from MARKED.
NOT_YET_SERIALISED: set[tuple[object, str]] = set()


def reads_the_clock(fn: object, _seen: set[int] | None = None) -> bool:
    """True if `fn`'s own body CALLS `time.perf_counter()` (or a bare `perf_counter()` reached
    through `from time import perf_counter`), or calls a plain module-level helper that does
    (recursively, one function at a time, cycle-guarded by object id). Structural — an `ast.Call`
    node whose target is literally named `perf_counter` — never a text search: this module's own
    fix-round-2 correction is that a naive `"perf_counter" in src` check matches THIS FUNCTION'S
    OWN source (the string appears here only because this docstring and the code below name it),
    which meant the walk in `tests/test_timing_marker.py` itself — reached once discovery stopped
    being a hand-picked module list — flagged this module's own test functions as candidates,
    tracing back through `_collect_candidates` to this docstring's literal text. An AST call-site
    match has no such blind spot: a docstring or a string comparison is never a `Call`.

    A class name called as a constructor (`AsyncClient(...)`) is not a function and is never
    recursed into; a name this cannot resolve to a plain function in the same module (a fixture, a
    builtin, an unimported name) simply does not match — it does not raise."""
    seen = _seen if _seen is not None else set()
    if not inspect.isfunction(fn) or id(fn) in seen:
        return False
    seen.add(id(fn))
    try:
        src = inspect.getsource(fn)
    except (OSError, TypeError):
        return False
    tree = ast.parse(textwrap.dedent(src))
    module = inspect.getmodule(fn)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "perf_counter":
            return True
        if isinstance(func, ast.Name):
            if func.id == "perf_counter":
                return True
            if module is not None and reads_the_clock(getattr(module, func.id, None), seen):
                return True
    return False


def _timing_marked(fn: object) -> bool:
    return any(m.name == "timing" for m in getattr(fn, "pytestmark", []))


def _collect_candidates() -> set[tuple[object, str]]:
    found = set()
    for module in _discover_test_modules():
        for name, obj in vars(module).items():
            if name.startswith("test_") and inspect.isfunction(obj) and reads_the_clock(obj):
                found.add((module, name))
    return found


def _qualname(pair: tuple[object, str]) -> str:
    module, name = pair
    return f"{module.__name__}::{name}"


def test_every_timing_budget_test_is_accounted_for():
    """Neither too broad nor gone stale in either direction: every test `reads_the_clock` matches
    is declared (in `MARKED` — `NOT_YET_SERIALISED` is empty since fix round 1), and nothing
    declared has stopped matching. With the gap closed this is exactly `candidates == MARKED`,
    checked as two one-directional differences so either kind of drift names its own offender."""
    candidates = _collect_candidates()
    declared = MARKED | NOT_YET_SERIALISED
    stale = sorted(_qualname(p) for p in declared - candidates)
    assert stale == [], (
        f"{stale} are declared here but `reads_the_clock` no longer matches them — the code "
        "changed under the declaration; update it."
    )
    new = sorted(_qualname(p) for p in candidates - declared)
    assert new == [], (
        f"{new} assert a real wall-clock time budget and are declared nowhere — a new "
        "timing-sensitive test. Mark it `@pytest.mark.timing` and add it to MARKED."
    )


def test_every_marked_timing_test_carries_the_pytest_mark():
    unmarked = sorted(
        _qualname((module, name)) for module, name in MARKED
        if not _timing_marked(vars(module)[name])
    )
    assert unmarked == [], f"{unmarked} assert a real wall-clock time budget but do not carry @pytest.mark.timing"


def test_the_not_yet_serialised_gap_stays_closed():
    """Fix round 1's ruling, pinned: the class this predicate finds runs alone, entirely — no
    tests are deferred. `NOT_YET_SERIALISED` stays declared (see its own comment) so a future
    exemption is a visible, deliberate edit to this file rather than a quiet omission from
    `MARKED` that `test_every_timing_budget_test_is_accounted_for` would wave through as "declared
    somewhere"."""
    assert NOT_YET_SERIALISED == set(), (
        f"NOT_YET_SERIALISED is no longer empty ({sorted(_qualname(p) for p in NOT_YET_SERIALISED)}) — "
        "fix round 1's ruling closed this gap; re-opening it needs the same kind of ruling, not a "
        "quiet addition."
    )
