import re
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extensions
import pytest

from app.config import settings
from scripts import migrate

ROOT = Path(__file__).resolve().parent.parent


def test_migrate_module_is_the_one_shared_scripts_migrate_module():
    """Regression guard (Task I1 re-review, hygiene item 1): this file used to load
    scripts/migrate.py a second time under a detached module name via
    importlib.util.spec_from_file_location, distinct from the `scripts.migrate` that
    tests/conftest.py's `scratch_dsn` fixture (and app code) import normally — a patch
    applied to one was invisible through the other. `migrate` above must now be the
    exact same module object."""
    import scripts.migrate as shared

    assert migrate is shared


def _maintenance_dsn(dsn: str) -> str:
    return dsn.rsplit("/", 1)[0] + "/postgres"


@pytest.fixture
def scratch_db():
    """A brand-new database per test so 'first run applies, second run skips' is real."""
    name = f"pm_test_{uuid.uuid4().hex[:8]}"
    admin = psycopg2.connect(_maintenance_dsn(settings.database_url))
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f'CREATE DATABASE "{name}"')
    dsn = settings.database_url.rsplit("/", 1)[0] + f"/{name}"
    try:
        yield dsn
    finally:
        with admin.cursor() as cur:
            cur.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        admin.close()


def _all_migration_names() -> list[str]:
    """The full, current set of migrations/NNN_*.sql files, in apply order — used
    instead of a hardcoded list so this test does not need editing every time a new
    migration is added to the shared migrations/ directory (Task I1 added 010-014)."""
    return [Path(p).name for p in migrate.migration_files()]


def test_applies_each_file_once_and_records_it(scratch_db):
    first = migrate.run(scratch_db)
    second = migrate.run(scratch_db)
    assert first == _all_migration_names()
    assert second == []
    with psycopg2.connect(scratch_db) as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM schema_migrations ORDER BY name")
        assert [r[0] for r in cur.fetchall()] == _all_migration_names()
        cur.execute("SELECT postgis_version()")
        assert cur.fetchone()[0].startswith("3.")


def test_002_creates_interest_signup_with_a_unique_normalised_email(scratch_db):
    applied = migrate.run(scratch_db)
    assert applied == _all_migration_names()
    with psycopg2.connect(scratch_db) as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO interest_signup (email, email_normalised, consent_version) VALUES ('A@x.com', 'a@x.com', 'coming-soon-v1')")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute("INSERT INTO interest_signup (email, email_normalised, consent_version) VALUES ('a@X.com', 'a@x.com', 'coming-soon-v1')")


def test_failing_file_raises_and_is_not_recorded(scratch_db, tmp_path):
    (tmp_path / "001_bad.sql").write_text("SELECT 1 FROM table_that_does_not_exist;")
    with pytest.raises(psycopg2.Error):
        migrate.run(scratch_db, directory=tmp_path)
    with psycopg2.connect(scratch_db) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM schema_migrations")
        assert cur.fetchone()[0] == 0


def test_normalize_dsn_strips_the_asyncpg_dialect():
    assert migrate.normalize_dsn("postgresql+asyncpg://u:p@h/db") == "postgresql://u:p@h/db"
    assert migrate.normalize_dsn("postgresql://u:p@h/db") == "postgresql://u:p@h/db"


def test_normalize_dsn_accepts_the_legacy_postgres_scheme():
    """Railway's PostGIS template emits postgres://, not postgresql:// (fix round 5).
    libpq/psycopg2 already accept it, but normalise it here too for robustness — same
    psycopg2-ready form either way."""
    assert migrate.normalize_dsn("postgres://u:p@h:5432/db") == migrate.normalize_dsn("postgresql://u:p@h:5432/db")
    assert migrate.normalize_dsn("postgres://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"


class _RaisingOnLedgerInsertCursor(psycopg2.extensions.cursor):
    """A cursor that raises the moment the ledger row would be inserted, so a test can
    prove the migration file's own SQL rolls back too (they must commit as one
    transaction)."""

    def execute(self, query, vars=None):  # matches psycopg2's own cursor.execute signature (shadows the builtin, intentionally)
        if isinstance(query, str) and "INSERT INTO schema_migrations" in query:
            raise psycopg2.Error("forced failure (RED/behavioural test): ledger insert")
        return super().execute(query, vars)


def test_apply_and_record_commit_as_one_transaction(scratch_db, tmp_path, monkeypatch):
    """Fix round 1 (Important, plan-mandated): if the ledger INSERT fails, the
    migration file's own SQL must not be left committed either."""
    (tmp_path / "002_tmp.sql").write_text("CREATE TABLE tmp_probe (id int);")
    real_connect = psycopg2.connect

    def connect_with_raising_cursor(dsn):
        return real_connect(dsn, cursor_factory=_RaisingOnLedgerInsertCursor)

    monkeypatch.setattr(migrate.psycopg2, "connect", connect_with_raising_cursor)

    with pytest.raises(psycopg2.Error):
        migrate.run(scratch_db, directory=tmp_path)

    with real_connect(scratch_db) as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('tmp_probe')")
        assert cur.fetchone()[0] is None, "the migration's own CREATE TABLE must have rolled back too"
        cur.execute("SELECT count(*) FROM schema_migrations WHERE name = %s", ("002_tmp.sql",))
        assert cur.fetchone()[0] == 0


def test_main_returns_2_and_names_the_missing_variable_on_stderr(monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    code = migrate.main()
    assert code == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_main_returns_0_and_applies_nothing_on_a_second_run(scratch_db, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", scratch_db)
    first_code = migrate.main()
    assert first_code == 0
    capsys.readouterr()  # discard the first run's output

    second_code = migrate.main()
    assert second_code == 0
    assert "done — 0 applied" in capsys.readouterr().out


def test_main_returns_3_when_the_database_is_unreachable(monkeypatch, capsys):
    """start.sh retries exit 3 (unreachable) but stops on any other failure (a broken migration file)."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@127.0.0.1:1/x")
    code = migrate.main()
    assert code == 3
    err = capsys.readouterr().err
    assert "unreachable" in err and "OperationalError" in err


def test_migration_files_never_manage_their_own_transaction():
    """I7 fix round 1: scripts/migrate.py commits each file's own SQL and its ledger
    row as ONE transaction; a migration that opened/closed its own transaction would
    silently break that atomicity. Regex matches BEGIN/COMMIT/ROLLBACK at a statement
    start (start of file or right after a `;`), case-insensitive, ignoring `--`
    line comments — a migration's own transaction-control statement, not the `BEGIN`
    a PL/pgSQL function body uses as a block delimiter (014_audit_log.sql has one)."""
    forbidden = re.compile(r"(?:^|;)\s*(begin|commit|rollback)\b", re.IGNORECASE)
    for path in sorted(ROOT.glob("migrations/*.sql")):
        text = "\n".join(line.split("--", 1)[0] for line in path.read_text(encoding="utf-8").splitlines())
        match = forbidden.search(text)
        assert not match, f"{path.name} must not manage its own transaction: {match.group(0)!r}"


def test_scratch_dsn_cleans_up_when_migrate_run_fails(request, monkeypatch):
    """I5 fix round 1: tests/conftest.py's `scratch_dsn` fixture must run `migrate.run`
    inside its `try` so a failing migration doesn't leak the just-created `pm_test_*`
    database (or the admin connection) on the compose Postgres every worktree on port
    5433 shares. `scratch_dsn` resolves `scripts.migrate` via a normal, cached import
    (scripts/ is a namespace package), so patching `.run` here reaches the exact
    function it calls through. `uuid.uuid4` is pinned so this test checks one specific,
    deterministic database name rather than scanning for any `pm_test_%` — the compose
    Postgres is shared with other concurrently-running test processes on this port, so
    a global scan can see (and misattribute) an unrelated, legitimately in-flight
    scratch database from one of those."""
    fixed = uuid.UUID("00000000-0000-0000-0000-0000000000fe")
    monkeypatch.setattr(uuid, "uuid4", lambda: fixed)
    expected_name = f"pm_test_{fixed.hex[:8]}"

    def _raise(dsn):
        raise RuntimeError("forced failure (RED/behavioural test): migrate.run")

    monkeypatch.setattr(migrate, "run", _raise)

    with pytest.raises(RuntimeError):
        request.getfixturevalue("scratch_dsn")

    admin = psycopg2.connect(_maintenance_dsn(settings.database_url))
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (expected_name,))
            assert cur.fetchall() == []
    finally:
        admin.close()


def test_scratch_dsn_normalises_an_asyncpg_style_dsn_with_a_query_string(request, monkeypatch):
    """M9 fix round 1: `settings.database_url` may be in the asyncpg-dialect,
    query-string form `app/db.py`/`app/checks.py` already accept — `scratch_dsn` must
    normalise it (as `db.sync_conn()`/`migrate.normalize_dsn()` do) rather than handing
    psycopg2 a scheme/query string it cannot parse."""
    asyncpg_style = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1) + "?sslmode=disable"
    monkeypatch.setattr(settings, "database_url", asyncpg_style)

    dsn = request.getfixturevalue("scratch_dsn")
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)
