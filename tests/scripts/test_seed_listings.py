"""scripts/seed_listings.py against a scratch database (spec 2026-09-06 D7, amendments A-L4/A-L5)."""
import json
import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest

from scripts import seed_listings as SL

ROOT = Path(__file__).resolve().parent.parent.parent


def _count(dsn: str, where: str = "TRUE") -> int:
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        # `where` is always a literal written in this file — never a value from a request.
        cur.execute(f"SELECT count(*) FROM listing WHERE {where}")
        return int(cur.fetchone()[0])


def _plant(dsn: str, slug: str, source: str) -> None:
    """One extra row, the way A-L4's matrix needs it. `source` is constrained by
    migrations/016_listing.sql to 'seed' | 'seller', so 'seller' IS the "any other source" row
    A-L4 asks for — a 'member' row cannot exist in this table at all."""
    with psycopg2.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, status)"
            " VALUES (%s,'Planted listing','Austin','TX','Austin','Small animal','Austin, TX',%s,'published')",
            (slug, source),
        )


def test_seed_writes_eighteen_published_seed_rows(scratch_dsn: str) -> None:
    assert SL.seed(scratch_dsn) == 18
    assert _count(scratch_dsn) == 18
    assert _count(scratch_dsn, "source = 'seed' AND status = 'published'") == 18


def test_seed_is_idempotent(scratch_dsn: str) -> None:
    SL.seed(scratch_dsn)
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT id, created_at FROM listing ORDER BY slug")
        before = cur.fetchall()
    assert SL.seed(scratch_dsn) == 18
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT id, created_at FROM listing ORDER BY slug")
        after = cur.fetchall()
    assert _count(scratch_dsn) == 18
    assert after == before, "an upsert by slug must keep the same row, id and created_at"
    # A-L5: name_disclosed is written from each row's own JSON value, on every import.
    hospitals = {h["slug"]: h for h in SL.load_seed(SL.SEEDS_FILE)}
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT slug, name_disclosed FROM listing")
        disclosed = dict(cur.fetchall())
    assert disclosed == {slug: h["name_disclosed"] for slug, h in hospitals.items()}
    assert all(disclosed.values()), "John's eighteen demo hospitals show their names on QA (A-L5)"


def test_reset_removes_seed_rows_but_never_seller_rows(scratch_dsn: str) -> None:
    SL.seed(scratch_dsn)
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO listing (slug, name, city, state, area, type, market, source, status)"
            " VALUES ('sellers-own','Seller listing','Austin','TX','Austin','Small animal','Austin, TX','seller','published')"
        )
    assert SL.seed(scratch_dsn, reset=True) == 18
    assert _count(scratch_dsn, "source = 'seed'") == 18
    assert _count(scratch_dsn, "source = 'seller'") == 1


def test_every_row_carries_the_seed_files_own_values(scratch_dsn: str) -> None:
    SL.seed(scratch_dsn)
    hospitals = {h["slug"]: h for h in SL.load_seed(SL.SEEDS_FILE)}
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT slug, name, street, city, state, zip, phone, hours, area, market, type, status,"
            " source, location_disclosed, price, rev, docs, rooms, sqft, bldg, est, note, staff,"
            " services, facility, ownership FROM listing"
        )
        for row in cur.fetchall():
            h = hospitals[row[0]]
            # M9: `status` and `location_disclosed` come from the FILE, not from a literal —
            # otherwise the day a row is authored `location_disclosed: false` this passes while
            # the seeder is what decides. `source` stays a literal: the script hard-codes 'seed'
            # and deliberately ignores the file's own value.
            assert row[1:14] == (
                h["name"], h["street"], h["city"], h["state"], h["zip"], h["phone"], h["hours"],
                h["area"], h["market"], h["type"], h["status"], "seed", h["location_disclosed"],
            ), h["slug"]
            assert row[14:] == (
                h["price"], h["rev"], h["docs"], h["rooms"], h["sqft"], h["bldg"], h["est"],
                h["note"], h["staff"], h["services"], h["facility"], h["ownership"],
            ), h["slug"]


def test_the_point_is_stored_longitude_first(scratch_dsn: str) -> None:
    """ST_MakePoint takes (x, y) = (lng, lat). Swapping them passes every test that does not
    read the geometry back — so this one reads it back."""
    SL.seed(scratch_dsn)
    hospitals = {h["slug"]: h for h in SL.load_seed(SL.SEEDS_FILE)}
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT slug, ST_Y(geom::geometry), ST_X(geom::geometry) FROM listing")
        for slug, lat, lng in cur.fetchall():
            assert round(float(lat), 6) == hospitals[slug]["lat"], slug
            assert round(float(lng), 6) == hospitals[slug]["lng"], slug


def test_listed_at_is_computed_from_listed_days_ago(scratch_dsn: str) -> None:
    SL.seed(scratch_dsn)
    hospitals = {h["slug"]: h for h in SL.load_seed(SL.SEEDS_FILE)}
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT slug, EXTRACT(DAY FROM now() - listed_at)::int FROM listing")
        for slug, days in cur.fetchall():
            assert days == hospitals[slug]["listed_days_ago"], slug


def test_photos_come_from_the_committed_inventory(scratch_dsn: str) -> None:
    """A-L10: the list is POSITIONAL — the first six entries are the design's six slots, `null`
    where the folder was too thin to fill one — so `p.photos[i]` still fills the design's slot `i`
    (A12.2). A-L11: it is no longer six LONG. Every photograph of the folder is in it, so the
    committed inventory is the only thing that decides how many a hospital has."""
    SL.seed(scratch_dsn)
    index = json.loads(SL.PHOTO_INDEX.read_text(encoding="utf-8"))["hospitals"]
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT slug, photos FROM listing")
        for slug, photos in cur.fetchall():
            assert photos == [
                None if e["file"] is None else f"{slug}/{e['file']}" for e in index[slug]
            ], slug
            assert len(photos) >= 6, slug   # the design's six photo slots (A-L9), and then some
    # …and A-L11 really did keep everything: 195 photographs, not one empty slot among them.
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM listing, jsonb_array_elements(photos) e WHERE e = 'null'")
        assert int(cur.fetchone()[0]) == 0, "A-L11 drops no photograph and leaves no slot empty"
        cur.execute("SELECT sum(jsonb_array_length(photos)) FROM listing")
        assert int(cur.fetchone()[0]) == 195


def test_photo_captions_are_written_in_step_with_the_photographs(scratch_dsn: str) -> None:
    """A-L11 (John, 2026-09-09: "have the user articulate what it is"). A photograph carries its
    OWN description; the design's fixed slot caption is only the fallback for a slot with none.
    The column is parallel to `photos` — same length, same positions — because amendment A15 reads
    the two by the same index."""
    SL.seed(scratch_dsn)
    index = json.loads(SL.PHOTO_INDEX.read_text(encoding="utf-8"))["hospitals"]
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT slug, photos, photo_captions FROM listing")
        for slug, photos, captions in cur.fetchall():
            assert captions == [e["caption"] for e in index[slug]], slug
            assert len(captions) == len(photos), slug
    # …and the UPSERT's second half writes it too, or a re-seed would leave yesterday's captions.
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("UPDATE listing SET photo_captions = '[]'::jsonb")
    SL.seed(scratch_dsn)
    with psycopg2.connect(scratch_dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM listing WHERE photo_captions = '[]'::jsonb")
        assert int(cur.fetchone()[0]) == 0, "the ON CONFLICT half does not update photo_captions"


def test_main_seeds_from_the_environment(scratch_dsn: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert SL.main([]) == 0
    assert _count(scratch_dsn) == 18
    assert SL.main(["--reset"]) == 0
    assert _count(scratch_dsn) == 18


def test_main_returns_two_without_a_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert SL.main([]) == 2


def test_main_returns_three_when_the_database_is_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    assert SL.main([]) == 3


def test_main_returns_four_when_the_database_refuses_the_import(
    scratch_dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """L4 review M4: every psycopg2.Error that is not an OperationalError used to escape as a
    traceback and exit 1. The realistic one is an UNMIGRATED database — `railway ssh` into a
    container whose migrations failed, or a one-off `start.sh seed`, which (unlike the `api`
    role) does not run scripts/migrate.py first: `listing` does not exist and psycopg2 raises
    UndefinedTable, a ProgrammingError. Simulated by pointing the first statement at a table
    that is not there, which is exactly what an unmigrated database looks like."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(SL, "COLLISION_CHECK", "SELECT slug FROM no_such_table WHERE slug = ANY(%s)")
    assert SL.main([]) == 4
    err = capsys.readouterr().err
    assert "UndefinedTable" in err and "42P01" in err, err


def test_main_returns_four_when_the_seed_file_is_malformed(
    scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = tmp_path / "hospitals.json"
    broken.write_text('{"version": 1}', encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(SL, "SEEDS_FILE", broken)
    assert SL.main([]) == 4


def test_main_returns_four_when_the_seed_file_is_absent(
    scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(SL, "SEEDS_FILE", tmp_path / "absent.json")
    assert SL.main([]) == 4


def test_photo_paths_is_empty_for_an_unknown_slug() -> None:
    assert SL.photo_paths("not-a-hospital", {"hospitals": {}}) == []


def test_photo_captions_are_the_inventorys_own_descriptions() -> None:
    """The unit: one caption per position, `None` where the position holds no photograph — so the
    two arrays stay index-for-index parallel however thin the folder was."""
    index = {"hospitals": {"h": [
        {"slot": "exterior", "file": "1.webp", "caption": "Exterior — front"},
        {"slot": "lobby", "file": None, "caption": None},
        {"slot": None, "file": "3.webp", "caption": "Interior — pharmacy"},
    ]}}
    assert SL.photo_captions("h", index) == ["Exterior — front", None, "Interior — pharmacy"]
    assert SL.photo_captions("not-a-hospital", {"hospitals": {}}) == []


def test_photo_captions_names_the_slug_whose_entry_is_unusable() -> None:
    with pytest.raises(SL.SeedDataError) as exc:
        SL.photo_captions("abc_animal_hospital", {"hospitals": {"abc_animal_hospital": [{"file": "1.webp"}]}})
    assert "abc_animal_hospital" in str(exc.value)


def test_photo_paths_keeps_an_empty_slot_as_a_null_in_place(tmp_path: Path) -> None:
    """A-L10, the unit: a slot the curation left empty is stored as `null` AT ITS POSITION, never
    dropped. Dropping it would slide every later photograph up one slot and put it under someone
    else's caption — the exact mislabelling this hotfix exists to end."""
    index = {"hospitals": {"h": [
        {"slot": "exterior", "file": "1.webp"},
        {"slot": "lobby", "file": None},
        {"slot": "exam", "file": "3.webp"},
    ]}}
    assert SL.photo_paths("h", index) == ["h/1.webp", None, "h/3.webp"]


def test_normalize_dsn_agrees_with_the_migration_runner() -> None:
    """scripts/seed_listings.py duplicates normalize_dsn because it must run as a bare script
    inside the container (pre-flight C1). This pins the copy to the original. The runner is
    loaded by file path, the way tests/test_migrate.py already loads it."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("migrate_probe", ROOT / "scripts" / "migrate.py")
    assert spec is not None and spec.loader is not None
    migrate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migrate)
    for dsn in (
        "postgres://u:p@h:5432/db",
        "postgresql://u:p@h:5432/db",
        "postgresql+asyncpg://u:p@h:5432/db",
        "postgresql://u:p@h:5432/db?sslmode=require",
    ):
        assert SL.normalize_dsn(dsn) == migrate.normalize_dsn(dsn), dsn


def test_the_module_runs_as_a_bare_script_from_the_repo_root() -> None:
    """The container runs `python scripts/seed_listings.py`, which puts scripts/ — not the repo
    root — on sys.path. A package-relative import in this file is a QA-only crash that neither
    pytest nor runpy would catch, because both already have the repo root on the path
    (pre-flight C1). This is the test that would have caught it."""
    import os

    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "seed_listings.py")],
        capture_output=True, text=True, check=False, cwd=ROOT, env=env,
    )
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert "DATABASE_URL" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr and "Traceback" not in result.stderr


def test_the_module_runs_as_a_bare_script_from_any_working_directory(tmp_path: Path) -> None:
    """`railway ssh` drops the operator into /app, but a one-off Railway service command can
    start anywhere. ROOT is resolved from __file__, so neither the seed file nor the photo
    inventory depends on the working directory."""
    import os

    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "seed_listings.py")],
        capture_output=True, text=True, check=False, cwd=tmp_path, env=env,
    )
    assert result.returncode == 2, result.stderr


def test_main_returns_four_when_the_seed_file_has_no_hospitals(
    scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `not isinstance(...) or not hospitals` arm of load_seed — the two exit-4 tests above
    reach the `except` clause instead (pre-flight C2)."""
    empty = tmp_path / "hospitals.json"
    empty.write_text('{"version": 1, "hospitals": []}', encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(SL, "SEEDS_FILE", empty)
    assert SL.main([]) == 4


def test_main_returns_four_when_the_hospitals_key_is_not_a_list(
    scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half of the same `or` (pre-flight C2)."""
    wrong = tmp_path / "hospitals.json"
    wrong.write_text('{"version": 1, "hospitals": {"a": 1}}', encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(SL, "SEEDS_FILE", wrong)
    assert SL.main([]) == 4


def test_main_returns_four_when_the_photo_inventory_is_absent(
    scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_photo_index's own `raise SeedDataError` — nothing else perturbs PHOTO_INDEX
    (pre-flight C2)."""
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(SL, "PHOTO_INDEX", tmp_path / "absent.json")
    assert SL.main([]) == 4


def test_main_returns_four_when_the_photo_inventory_is_the_wrong_shape(
    scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L4 review M5: `hospitals` must be an object keyed by slug. A list there used to reach
    `.get(slug)` on a list and raise AttributeError — a traceback, not exit 4."""
    wrong = tmp_path / "index.json"
    wrong.write_text('{"version": 1, "hospitals": [{"file": "1.webp"}]}', encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(SL, "PHOTO_INDEX", wrong)
    assert SL.main([]) == 4


def test_main_returns_four_when_a_photo_entry_has_no_file(
    scratch_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L4 review M5, the other half: an inventory entry missing `file` used to raise KeyError out
    of photo_paths. It is malformed seed data, so it is exit 4 and it names the slug."""
    slug = str(SL.load_seed(SL.SEEDS_FILE)[0]["slug"])
    broken = tmp_path / "index.json"
    broken.write_text(json.dumps({"version": 1, "hospitals": {slug: [{"caption": "no file key"}]}}), encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    monkeypatch.setattr(SL, "PHOTO_INDEX", broken)
    assert SL.main([]) == 4


def test_photo_paths_names_the_slug_whose_entry_is_unusable() -> None:
    with pytest.raises(SL.SeedDataError) as exc:
        SL.photo_paths("abc_animal_hospital", {"hospitals": {"abc_animal_hospital": [{"caption": "x"}]}})
    assert "abc_animal_hospital" in str(exc.value)


def test_row_params_names_the_missing_field() -> None:
    """row_params' `except KeyError` arm (pre-flight C2)."""
    with pytest.raises(SL.SeedDataError) as exc:
        SL.row_params({"slug": "x"}, [], [])
    assert "x" in str(exc.value) and "name" in str(exc.value)


def test_the_main_guard_is_covered(monkeypatch: pytest.MonkeyPatch) -> None:
    """runpy re-executes the file in THIS process with __name__ == "__main__", so pytest-cov
    sees the guard; the subprocess tests above prove the same entry point works when the repo
    root is NOT on sys.path, which coverage can never see."""
    import runpy

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["seed_listings.py"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(ROOT / "scripts" / "seed_listings.py"), run_name="__main__")
    assert exc.value.code == 2


# --- A-L4 (John, 2026-09-08: "must remove the old seeded data when importing the new data") ---
# Removal is UNCONDITIONAL on every import, in the same transaction as the upsert; --reset stays
# as the documented full wipe. Rows with any other `source` are never touched by either path.


def test_a_stale_seed_row_is_removed_by_a_plain_import(scratch_dsn: str) -> None:
    """A-L4: a `source='seed'` row whose slug is no longer in seeds/hospitals.json goes, with no
    --reset — otherwise QA keeps yesterday's hospitals beside today's."""
    _plant(scratch_dsn, "withdrawn-last-week", "seed")
    assert _count(scratch_dsn, "slug = 'withdrawn-last-week'") == 1
    assert SL.seed(scratch_dsn) == 18
    assert _count(scratch_dsn, "slug = 'withdrawn-last-week'") == 0
    assert _count(scratch_dsn, "source = 'seed'") == 18


def test_a_non_seed_row_survives_a_plain_import(scratch_dsn: str) -> None:
    """A-L4, the other mode: `source` is constrained to 'seed' | 'seller' by
    migrations/016_listing.sql, so a seller's own listing is every non-seed row there can be."""
    _plant(scratch_dsn, "sellers-own", "seller")
    assert SL.seed(scratch_dsn) == 18
    assert _count(scratch_dsn, "source = 'seller'") == 1
    assert _count(scratch_dsn, "source = 'seed'") == 18


def test_reset_on_an_empty_table_still_seeds_eighteen(scratch_dsn: str) -> None:
    """A-L4: --reset is a full wipe of the seed rows and then the import — on a table that has
    none, it is simply the import."""
    assert SL.seed(scratch_dsn, reset=True) == 18
    assert _count(scratch_dsn, "source = 'seed' AND status = 'published'") == 18


def test_the_summary_line_reports_inserted_updated_and_removed(
    scratch_dsn: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """A-L4: "the exit summary prints inserted / updated / removed counts"."""
    _plant(scratch_dsn, "withdrawn-last-week", "seed")
    SL.seed(scratch_dsn)
    assert "[seed] inserted 18, updated 0, removed 1" in capsys.readouterr().out
    SL.seed(scratch_dsn)
    assert "[seed] inserted 0, updated 18, removed 0" in capsys.readouterr().out
    SL.seed(scratch_dsn, reset=True)
    assert "[seed] inserted 18, updated 0, removed 18" in capsys.readouterr().out


def test_main_refuses_when_the_environment_is_not_declared(
    scratch_dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """L4 review I1: `ENVIRONMENT` unset must FAIL CLOSED. scripts/bootstrap_admin.py reads
    `settings.environment`, which app/config.py declares with no default, so a missing variable
    stops it at import; keying on `os.environ.get(..., "")` here would let the same operator —
    production's DATABASE_URL exported on a laptop, ENVIRONMENT forgotten — seed the
    stakeholders' database with demo hospitals."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert SL.main([]) == 2
    captured = capsys.readouterr()
    assert "ENVIRONMENT" in captured.err
    assert captured.out == "", "a refusal says nothing on stdout"
    assert _count(scratch_dsn) == 0, "the refusal must happen before anything is opened"
    # ...and before the connection, as the production refusal does: an unreachable DSN still 2.
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    assert SL.main([]) == 2


def test_main_refuses_to_run_against_production(
    scratch_dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """"Never on production without John's go" (D7), enforced the way scripts/bootstrap_admin.py
    enforces its own: exit 2, on stderr, naming the flag, before anything is opened."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert SL.main([]) == 2
    captured = capsys.readouterr()
    assert "--production" in captured.err and "production" in captured.err
    assert captured.out == "", "a refusal says nothing on stdout"
    assert _count(scratch_dsn) == 0, "the production refusal must happen before any write"
    # ...and before the CONNECTION: an unreachable database still gets 2, never 3.
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    assert SL.main([]) == 2


def test_production_runs_when_the_operator_says_it_out_loud(
    scratch_dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """John's go, spelled the way scripts/bootstrap_admin.py spells it (`--production`): the run
    proceeds, and says on its FIRST line of stdout which environment it is writing to."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert SL.main(["--production"]) == 0
    assert _count(scratch_dsn, "source = 'seed'") == 18
    assert "production" in capsys.readouterr().out.splitlines()[0].lower()


def test_the_production_flag_is_harmless_anywhere_else(
    scratch_dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Passing it on QA is not an error and does not announce a production run."""
    monkeypatch.setenv("ENVIRONMENT", "qa")
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert SL.main(["--production", "--reset"]) == 0
    assert _count(scratch_dsn, "source = 'seed'") == 18
    assert "production" not in capsys.readouterr().out.lower()


def test_a_non_seed_listing_on_a_seed_slug_stops_the_import(
    scratch_dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """L4 review round 1: the seeder must never rewrite a listing it does not own. The check runs
    BEFORE the upsert (one SELECT of the colliding slugs), so the refusal names every offender at
    once and nothing in the transaction commits."""
    taken = str(SL.load_seed(SL.SEEDS_FILE)[0]["slug"])
    _plant(scratch_dsn, taken, "seller")
    _plant(scratch_dsn, "withdrawn-last-week", "seed")   # a successful import would delete this
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert SL.main([]) == 5
    err = capsys.readouterr().err
    assert taken in err, err
    assert "non-seed" in err, err
    # All-or-nothing: the seller row is untouched, the stale seed row was NOT deleted, and not
    # one of the eighteen was written.
    assert _count(scratch_dsn) == 2
    assert _count(scratch_dsn, "source = 'seller'") == 1
    assert _count(scratch_dsn, "slug = 'withdrawn-last-week'") == 1


def test_the_scoped_upsert_is_the_backstop_when_the_precheck_sees_nothing(
    scratch_dsn: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`ON CONFLICT (slug) DO UPDATE … WHERE listing.source = 'seed'` is the second line of
    defence — for a row inserted by another transaction after the pre-check has run. The scoped
    UPDATE matches nothing there, and a zero-row upsert must FAIL LOUDLY rather than skip a
    listing in silence. Simulated by blinding the pre-check, which is the only way to reach the
    arm without a real race."""
    taken = str(SL.load_seed(SL.SEEDS_FILE)[0]["slug"])
    _plant(scratch_dsn, taken, "seller")
    monkeypatch.setattr(SL, "COLLISION_CHECK", "SELECT slug FROM listing WHERE false AND slug = ANY(%s)")
    monkeypatch.setenv("DATABASE_URL", scratch_dsn)
    assert SL.main([]) == 5
    assert taken in capsys.readouterr().err
    assert _count(scratch_dsn) == 1, "the whole transaction rolls back"
    assert _count(scratch_dsn, "source = 'seller'") == 1
