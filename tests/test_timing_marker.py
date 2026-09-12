"""Task CI-TIMING. Four tests measure real wall-clock budgets against a live Postgres/Redis and a
real ASGI app — three constant-time auth checks (a network-timing side channel, `tests/api/
test_auth.py`) and one p95 latency gate on a forced principal-cache miss (`tests/perf/
test_api_latency.py`). All four passed 5/5 in isolation and failed on a loaded 20-stack developer
machine in the same run, twice: they were scheduled beside CPU-heavy tests (Argon2id hashing,
media encoding, Census geometry) and so measured the machine, not the code. The budgets themselves
are correct and untouched by this task — what moves is WHEN they run: `@pytest.mark.timing`
(registered in `pyproject.toml`) pulls them out of the normal run and into a second, serial, LAST
step of the gate (`-m timing -p no:randomly`, coverage appended onto the first step's — see
CLAUDE.md's Common operations and `.github/workflows/quality.yml`).

This module is the RED-first proof that the marker is actually on every test that needs it, and
the mechanism a NEW timing-sensitive test is caught by if its author forgets the marker.

THE PREDICATE (`reads_the_clock`, below) is structural, not a hand-typed list of the four names — a
hand-typed list could recite the past but could not "catch a new timing test": a test reads the
wall clock if its own source contains `time.perf_counter()`, or if it calls a plain
(module-level-resolvable) helper that does, recursively — the one hop this project's own shape
needs once, for `test_p95_within_budget`, whose `measure()` closure calls the shared `_samples()`
helper rather than reading the clock inline. Every OTHER budgeted test in `test_api_latency.py`
reads the clock directly inside its own inline `measure()` closure, so the recursion is exercised
by exactly the one case that needs it — not a speculative allowance.

Applied across the whole suite (not just the two files the incident named), the predicate finds
THIRTEEN tests, not four:

  * the three constant-time auth checks plus a fourth, structurally identical sibling
    (`test_signin_failures_are_generic_for_wrong_unknown_suspended_and_revoked`) that carries a
    5x looser tolerance (100 ms of pairwise median spread against the trio's 20 ms) and has not
    been reported flaking;
  * eight p95-budgeted tests in `test_api_latency.py` — `test_cold_principal_cache_me_p95_within_
    budget` plus seven others that assert through the very same `gate_p95` helper (that function's
    own docstring: "The p95 gate every latency test asserts through"), one of which
    (`test_p95_within_budget[/api/healthz-20]`) is on record flaking once today too;
  * two more elsewhere in the suite that assert a real, if generous, wall-clock ceiling:
    `tests/test_db.py::test_check_db_and_check_redis_time_out_against_a_black_hole` (a literal
    `budget` variable) and `tests/auth/test_passwords.py::test_argon2id_parameters_hash_verify_
    rehash_and_cost` (a single Argon2id verify under 250 ms).

`MARKED` is the four this task actually moves. `NOT_YET_SERIALISED` is the other nine: the
predicate calls them out honestly rather than silently only checking the four this task happens to
fix, and it is checked in BOTH directions below — the same two-way discipline `tests/test_docs.py`'s
`no_clause` set uses for CLAUDE.md's literal-edit clauses — so a test that starts carrying the
marker (no longer a gap) or a test the predicate stops matching (a stale declaration) both fail
loud rather than silently drifting. A genuinely NEW timing test — one that reads the clock, one
hop or none — is caught the moment it is written: it satisfies the predicate, it is declared in
neither set, and `test_every_timing_budget_test_is_accounted_for` fails, by name, until a human
decides which list it belongs in.
"""
import ast
import inspect
import textwrap

from tests import test_db
from tests.api import test_auth
from tests.auth import test_passwords
from tests.perf import test_api_latency

MODULES = (test_auth, test_api_latency, test_db, test_passwords)

# The four tests this task marks `@pytest.mark.timing` and moves to the gate's serial, last step.
MARKED = {
    (test_auth, "test_signup_does_the_same_work_for_a_new_and_an_existing_address"),
    (test_auth, "test_the_re_issue_branch_answers_in_the_same_time_as_the_account_exists_branch"),
    (test_auth, "test_a_new_address_and_an_existing_unverified_one_answer_in_the_same_time"),
    (test_api_latency, "test_cold_principal_cache_me_p95_within_budget"),
}

# Everything else `reads_the_clock` matches (see the module docstring for why each is here rather
# than in `MARKED`). Declared so the gap is a decision on record, not a silent hole in the scan.
NOT_YET_SERIALISED = {
    (test_auth, "test_signin_failures_are_generic_for_wrong_unknown_suspended_and_revoked"),
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


def reads_the_clock(fn: object, _seen: set[int] | None = None) -> bool:
    """True if `fn`'s own source contains `time.perf_counter()`, or if it calls a plain
    module-level helper that does (recursively, one function at a time, cycle-guarded by object
    id). A class name called as a constructor (`AsyncClient(...)`) is not a function and is never
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
    if "perf_counter" in src:
        return True
    module = inspect.getmodule(fn)
    if module is None:
        return False
    tree = ast.parse(textwrap.dedent(src))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            callee = getattr(module, node.func.id, None)
            if reads_the_clock(callee, seen):
                return True
    return False


def _timing_marked(fn: object) -> bool:
    return any(m.name == "timing" for m in getattr(fn, "pytestmark", []))


def _collect_candidates() -> set[tuple[object, str]]:
    found = set()
    for module in MODULES:
        for name, obj in vars(module).items():
            if name.startswith("test_") and inspect.isfunction(obj) and reads_the_clock(obj):
                found.add((module, name))
    return found


def _qualname(pair: tuple[object, str]) -> str:
    module, name = pair
    return f"{module.__name__}::{name}"


def test_every_timing_budget_test_is_accounted_for():
    """Neither too broad nor gone stale in either direction: every test `reads_the_clock` matches
    is in exactly one of `MARKED` / `NOT_YET_SERIALISED`, and nothing declared there has stopped
    matching."""
    candidates = _collect_candidates()
    declared = MARKED | NOT_YET_SERIALISED
    stale = sorted(_qualname(p) for p in declared - candidates)
    assert stale == [], (
        f"{stale} are declared here but `reads_the_clock` no longer matches them — the code "
        "changed under the declaration; update it."
    )
    new = sorted(_qualname(p) for p in candidates - declared)
    assert new == [], (
        f"{new} assert a real wall-clock time budget and are declared in neither MARKED nor "
        "NOT_YET_SERIALISED — a new timing-sensitive test. Decide: mark it "
        "`@pytest.mark.timing` (add to MARKED) or record why it waits (NOT_YET_SERIALISED)."
    )


def test_every_marked_timing_test_carries_the_pytest_mark():
    unmarked = sorted(
        _qualname((module, name)) for module, name in MARKED
        if not _timing_marked(vars(module)[name])
    )
    assert unmarked == [], f"{unmarked} assert a real wall-clock time budget but do not carry @pytest.mark.timing"


def test_not_yet_serialised_tests_have_not_quietly_started_carrying_the_mark():
    """The mirror of the assertion above. Nothing in the declared gap may quietly start carrying
    `@pytest.mark.timing` — that would make the declaration a lie; it belongs in `MARKED` instead,
    with the same care given to the four this task marks."""
    wrongly_marked = sorted(
        _qualname((module, name)) for module, name in NOT_YET_SERIALISED
        if _timing_marked(vars(module)[name])
    )
    assert wrongly_marked == [], f"{wrongly_marked} are declared NOT_YET_SERIALISED but now carry @pytest.mark.timing — move them to MARKED"
