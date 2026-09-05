import importlib.util
import uuid
from pathlib import Path

import psycopg2
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
