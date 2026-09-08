"""Census test fixtures.

Amended 2026-09-07 (Wave 2a Task I9a): `scratch_dsn` and `conn` are reused from the root
`tests/conftest.py`, not written here. Wave 2a needed the same create-migrate-drop database per
test and built it there, with two fixes this plan's draft did not have: `migrate.run` runs inside
the `try`, so a failing migration cannot leak the database and the admin connection on the shared
compose Postgres, and the DSN is normalised through `migrate.normalize_dsn()` before the database
name is split off, so an asyncpg-style or query-stringed `DATABASE_URL` does not break or bake its
query string into a database name. It also loads `scripts/migrate.py` as an ordinary
`from scripts import migrate` rather than through `importlib.util`, which is what lets a test patch
`scripts.migrate.run`.

Pytest fixtures defined in a parent directory's `conftest.py` are visible to tests in this
directory without re-declaring them, so `tests/census/test_schema.py` and
`tests/census/test_registry.py` ask for `conn` directly. This file carries only what is
census-specific — nothing yet.
"""
