"""The session-template database machinery in `tests/conftest.py` (platform task P-TDB).

`scratch_dsn` used to create an EMPTY database per test and run the whole migration ladder
into it — `CREATE EXTENSION postgis` and all — which made the migration ladder the suite's
wall-clock bottleneck (A-C0 ¶9: "remedy: session-scoped template DB if > 20"). It now clones a
database that was migrated ONCE for the session (`template_dsn`).

These tests hold the clone to the contract the per-test ladder met: the template is migrated
once and is the same one all session, every clone starts from the template's ledger, two clones
are independent of each other, `migrate.run` still runs exactly once against each clone (it is
the drift guard and the failure-injection seam, not the schema builder, now), the drop-on-failure
path still fires, a template something is connected to falls back to the old create-then-migrate
path with a warning rather than failing the run, and the template itself does not outlive the
session that built it.
"""
import os
import subprocess
import sys
import uuid
import warnings
from pathlib import Path

import psycopg2
import psycopg2.errorcodes
import psycopg2.errors
import pytest

from app.config import settings
from scripts import migrate
from tests.conftest import _clone_database, _maintenance, _normalized_base

ROOT = Path(__file__).resolve().parent.parent

# Every template name this module has been handed. `template_dsn` is session-scoped, so the two
# tests that append here must see ONE name between them — which is the only observable difference
# between "migrated once per session" and "migrated once per test".
SEEN_TEMPLATES: list[str] = []


def _base() -> str:
    return _normalized_base(migrate, settings.database_url)


def _ledger(dsn: str) -> list[str]:
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM schema_migrations ORDER BY name")
            return [row[0] for row in cur.fetchall()]
    finally:
        # Explicitly, not `with psycopg2.connect(...) as conn`: that context manager ends the
        # TRANSACTION and leaves the connection open, and a connection left open to the template
        # is exactly what makes the next `CREATE DATABASE ... TEMPLATE` fall back.
        conn.close()


def _all_migration_names() -> list[str]:
    return sorted(Path(p).name for p in migrate.migration_files())


def test_the_template_is_migrated_and_carries_the_whole_ledger(template_dsn):
    SEEN_TEMPLATES.append(template_dsn)
    assert template_dsn.startswith("pm_tmpl_")
    assert _ledger(f"{_base()}/{template_dsn}") == _all_migration_names()


def test_one_template_serves_the_whole_session(template_dsn):
    """Appends and asserts on the set, so the assertion is true when this test runs alone and
    only becomes interesting when the test above has run too — an ordering-free way to say
    "the same template", without reaching into pytest's fixture internals for the scope."""
    SEEN_TEMPLATES.append(template_dsn)
    assert len(set(SEEN_TEMPLATES)) == 1, f"more than one template in one session: {SEEN_TEMPLATES}"


def test_two_scratch_databases_are_independent_clones_of_the_template(request, template_dsn):
    """The second database is built with the fixture's OWN `_clone_database` and deliberately
    never migrated: if it comes up carrying the full ledger, the rows can only have been copied
    from the template, which is the proof that the clone is a clone."""
    first = request.getfixturevalue("scratch_dsn")

    second_name = f"pm_test_{uuid.uuid4().hex[:8]}"
    admin = psycopg2.connect(_maintenance(migrate, settings.database_url))
    admin.autocommit = True
    try:
        assert _clone_database(admin, second_name, template_dsn) is True
        second = f"{_base()}/{second_name}"

        assert _ledger(first) == _all_migration_names()
        assert _ledger(second) == _all_migration_names()

        probe = psycopg2.connect(first)
        probe.autocommit = True
        try:
            with probe.cursor() as cur:
                cur.execute("CREATE TABLE only_in_the_first ()")
        finally:
            probe.close()

        other = psycopg2.connect(second)
        try:
            with other.cursor() as cur:
                cur.execute("SELECT to_regclass('only_in_the_first')")
                assert cur.fetchone() == (None,), "the two clones share storage"
        finally:
            other.close()
    finally:
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{second_name}" WITH (FORCE)')
        admin.close()


def test_the_clone_still_runs_the_migrator_exactly_once_and_applies_nothing(request, monkeypatch, template_dsn):
    """`migrate.run` stays in `scratch_dsn` on purpose: on a clone it applies nothing and
    re-runs `refuse_changed_files`, so a tree that disagrees with the migrations already in the
    template is still refused per test — the same drift guard the per-test ladder was.
    `template_dsn` is requested as a fixture ARGUMENT so the template is built before the spy is
    installed; otherwise the spy would count the template's own migration too."""
    calls: list[str] = []
    real = migrate.run

    def spy(dsn, directory=None):
        calls.append(dsn)
        return real(dsn, directory)

    monkeypatch.setattr(migrate, "run", spy)
    dsn = request.getfixturevalue("scratch_dsn")

    assert calls == [dsn]
    assert real(dsn) == [], "the clone was not already fully migrated"


def test_a_failing_migrator_still_drops_the_clone(request, monkeypatch, template_dsn):
    """The drop-on-failure path of I5 fix round 1, re-pinned now that the database it has to
    remove is a POPULATED clone rather than an empty database (a clone is what `DROP DATABASE
    ... WITH (FORCE)` now has to take away, and it is created before `migrate.run` is reached).
    `tests/test_migrate.py::test_scratch_dsn_cleans_up_when_migrate_run_fails` is the same
    guarantee stated from the migrator's side; this one states it from the template's."""
    fixed = uuid.UUID("00000000-0000-0000-0000-0000000000fd")
    monkeypatch.setattr(uuid, "uuid4", lambda: fixed)
    expected = f"pm_test_{fixed.hex[:8]}"

    def explode(dsn, directory=None):
        raise RuntimeError("forced failure (behavioural test): migrate.run on a clone")

    monkeypatch.setattr(migrate, "run", explode)

    with pytest.raises(RuntimeError, match="forced failure"):
        request.getfixturevalue("scratch_dsn")

    admin = psycopg2.connect(_maintenance(migrate, settings.database_url))
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (expected,))
            assert cur.fetchall() == [], f"{expected} survived a failing migrate.run"
    finally:
        admin.close()


def test_a_template_in_use_falls_back_to_create_then_migrate(request, template_dsn):
    """Postgres will not copy a database another session is connected to. Provoked with a REAL
    connection to the template rather than a monkeypatched psycopg2 error, because the error
    text the fallback keys on ("source database ... is being accessed by other users") is
    Postgres's own and a stubbed one would only prove the stub. The scratch database that comes
    back must still be fully migrated — the fallback is the pre-template path, not a degraded
    one."""
    holder = psycopg2.connect(f"{_base()}/{template_dsn}")
    try:
        with pytest.warns(UserWarning, match="being accessed by other users"):
            dsn = request.getfixturevalue("scratch_dsn")
        assert _ledger(dsn) == _all_migration_names()
    finally:
        holder.close()


def test_an_unexpected_postgres_error_on_the_clone_propagates_unchanged():
    """`_clone_database` survives exactly ONE refusal — the template being in use. Every other
    error from `CREATE DATABASE ... TEMPLATE` is a real failure and has to reach the caller as
    itself, or a broken maintenance connection, a permissions problem or a typo'd template would
    be silently answered with a quietly-slower empty database.

    Provoked with a template name no database has: Postgres answers SQLSTATE 3D000
    (`InvalidCatalogName`), a different code from the 55006 the fallback keys on, so the arm is
    exercised by a real error rather than by a stub of one. Nothing may fall back — no warning,
    and no database of that name, because the fallback's own `CREATE DATABASE` would have made
    one. The maintenance connection must also still work afterwards, which is why the arm can
    re-raise without a rollback: it is in autocommit and never opened a transaction to poison."""
    name = f"pm_test_{uuid.uuid4().hex[:8]}"
    absent = f"pm_tmpl_absent_{uuid.uuid4().hex[:8]}"
    admin = psycopg2.connect(_maintenance(migrate, settings.database_url))
    admin.autocommit = True
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with pytest.raises(psycopg2.errors.InvalidCatalogName) as excinfo:
                _clone_database(admin, name, absent)

        assert excinfo.value.pgcode == psycopg2.errorcodes.INVALID_CATALOG_NAME
        assert absent in str(excinfo.value)
        assert "being accessed by other users" not in str(excinfo.value)
        assert [str(w.message) for w in caught] == [], "the unexpected error fell back instead of propagating"

        with admin.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
            assert cur.fetchall() == [], f"{name} was created by an arm that must create nothing"
    finally:
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


def test_the_session_that_built_the_template_drops_it(tmp_path):
    """The template outlives every test in the session, so the only place its DROP is observable
    is a session that has already ENDED. This runs one: a throwaway module in `tmp_path` that
    records the template's name, driven by a subprocess pytest with `tests/conftest.py` loaded as
    a PLUGIN (`-p tests.conftest`) — the module sits outside `tests/`, so pytest would not pick
    that conftest up by itself. Chosen over a `pytest_sessionfinish` hook in the suite's own
    conftest: a hook that fails is reported as an internal error rather than as a named test, and
    it would have to run for every session, including the ones that never build a template."""
    recorded = tmp_path / "template-name.txt"
    module = tmp_path / "test_records_the_template.py"
    module.write_text(
        "from pathlib import Path\n"
        "\n"
        "\n"
        "def test_records_the_template_name(template_dsn):\n"
        f"    Path({str(recorded)!r}).write_text(template_dsn)\n"
    )

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-c", "pyproject.toml",
         "-p", "no:cacheprovider", "-p", "tests.conftest", str(module)],
        cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    name = recorded.read_text()
    assert name.startswith("pm_tmpl_")
    admin = psycopg2.connect(_maintenance(migrate, settings.database_url))
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
            assert cur.fetchall() == [], f"{name} outlived the session that created it"
    finally:
        admin.close()
