import importlib.util
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extensions
import pytest

from app.config import settings

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("migrate", ROOT / "scripts" / "migrate.py")
migrate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate)  # type: ignore[union-attr]


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


def test_applies_each_file_once_and_records_it(scratch_db):
    first = migrate.run(scratch_db)
    second = migrate.run(scratch_db)
    assert first == ["001_init.sql"]
    assert second == []
    with psycopg2.connect(scratch_db) as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM schema_migrations ORDER BY name")
        assert [r[0] for r in cur.fetchall()] == ["001_init.sql"]
        cur.execute("SELECT postgis_version()")
        assert cur.fetchone()[0].startswith("3.")


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


class _RaisingOnLedgerInsertCursor(psycopg2.extensions.cursor):
    """A cursor that raises the moment the ledger row would be inserted, so a test can
    prove the migration file's own SQL rolls back too (they must commit as one
    transaction)."""

    def execute(self, query, vars=None):  # noqa: A002 - matches psycopg2's own param name
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
