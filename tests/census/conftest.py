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
census-specific — and, since Task A9, the one Wave 2a fixture that is NOT visible here because it
lives in a sibling directory's conftest (`member`, re-exported below).
"""

from tests.api import conftest as api_fixtures

# `member` — a real `account` row with the roles asked for, a live session and the matching CSRF
# header (Wave 2a, Task I9a). Re-exported rather than re-declared: `tests/census/test_admin_api.py`
# drives the admin Data Sources API over HTTP exactly as `tests/api/test_admin_users.py` drives the
# Users one, and a second definition of "a real signed-in account" is a second thing to keep in
# step with `app.auth.sessions`. A plain assignment (not a `from ... import member`, which ruff
# reads as an unused import) — pytest collects any conftest attribute that IS a fixture, under the
# name it is bound to.
member = api_fixtures.member
