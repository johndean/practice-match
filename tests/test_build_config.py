import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_dockerfile_declares_the_build_args_and_the_dispatcher_entrypoint():
    d = (ROOT / "Dockerfile").read_text()
    assert "ARG ENVIRONMENT" in d and "ARG COMMIT_SHA=dev" in d
    assert 'ENTRYPOINT ["bash", "scripts/start.sh"]' in d and 'CMD ["api"]' in d


def test_dockerfile_requires_an_explicit_environment_build_arg():
    d = (ROOT / "Dockerfile").read_text()
    assert "ARG ENVIRONMENT=" not in d, (
        "ENVIRONMENT must have NO default — a build that ever fails to receive it must fail "
        "loudly, not silently ship the qa bundle (prototype jump bar included) to production"
    )
    assert d.count("ARG ENVIRONMENT") == 2, "ENVIRONMENT must still be declared (with no default) in both stages"
    assert 'test -n "$ENVIRONMENT"' in d, (
        "the frontend stage must guard against a missing/empty ENVIRONMENT before `npm run build`"
    )


def test_dockerfile_runs_as_a_non_root_user_declared_after_the_last_copy():
    lines = (ROOT / "Dockerfile").read_text().splitlines()
    copy_lines = [i for i, line in enumerate(lines) if line.startswith("COPY")]
    user_lines = [i for i, line in enumerate(lines) if line.strip() == "USER app"]
    entrypoint_lines = [i for i, line in enumerate(lines) if line.startswith("ENTRYPOINT")]
    assert copy_lines, "Dockerfile has no COPY instructions"
    assert user_lines, "Dockerfile lacks a `USER app` line"
    assert entrypoint_lines, "Dockerfile lacks an ENTRYPOINT"
    assert max(copy_lines) < user_lines[0] < min(entrypoint_lines), (
        "USER app must come after the last COPY and before ENTRYPOINT"
    )


def test_railway_json_points_at_the_dispatcher_migrations_and_healthz():
    cfg = json.loads((ROOT / "railway.json").read_text())
    assert cfg["deploy"]["startCommand"] == "bash scripts/start.sh api"
    assert cfg["deploy"]["preDeployCommand"] == ["python scripts/migrate.py"]
    assert cfg["deploy"]["healthcheckPath"] == "/api/healthz"


def test_ignore_files_keep_secrets_tests_and_node_modules_out_of_uploads_and_images():
    for name in (".railwayignore", ".dockerignore"):
        text = (ROOT / name).read_text().split()
        for entry in ("frontend/node_modules", "tests", ".env", ".env.*", ".venv"):
            assert entry in text, f"{name} lacks {entry}"


def test_dockerfile_builds_the_coming_soon_page_in_its_own_stage():
    d = (ROOT / "Dockerfile").read_text()
    assert "FROM node:22-bookworm-slim AS coming-soon-build" in d
    assert "COPY coming-soon/package.json coming-soon/package-lock.json ./" in d
    assert "COPY --from=coming-soon-build /work/coming-soon/dist/ ./coming-soon/dist/" in d


def test_ignore_files_keep_the_coming_soon_build_and_modules_out():
    for name in (".railwayignore", ".dockerignore"):
        text = (ROOT / name).read_text().split()
        for entry in ("coming-soon/node_modules", "coming-soon/dist"):
            assert entry in text, f"{name} lacks {entry}"
    assert "coming-soon/dist/" in (ROOT / ".gitignore").read_text().split()
    assert "frontend/coverage/" in (ROOT / ".gitignore").read_text().split()


def test_coming_soon_build_emits_its_bundle_under_app_like_the_marketplace():
    # app/static.py mounts /_app at boot; without this the api crashes in coming-soon mode (11b, 2026-09-06).
    assert "assetsDir: '_app'" in (ROOT / "coming-soon" / "vite.config.js").read_text()


def test_dockerfile_ships_the_seed_data_and_photographs():
    """scripts/seed_listings.py runs inside the api container and app/api/listings.py serves
    the WebP files off disk, so seeds/ must be in the image (spec 2026-09-06 D3/D7)."""
    d = (ROOT / "Dockerfile").read_text()
    assert "COPY seeds/ ./seeds/" in d


def test_seed_data_is_not_ignored_by_the_image_or_upload_filters():
    """A tripwire, not a proof — scripts/verify-image.sh is what actually looks inside the built
    image. It catches every spelling of the exclusion, not just the bare token (L4 review M7):
    `seeds`, `seeds/`, `seeds/**`, `**/seeds`, `seeds/hospitals`. `.railwayignore` has no other
    backstop at all — verify-image.sh builds locally, so a regression there would first show up
    as a QA deploy with no photographs."""
    for name in (".railwayignore", ".dockerignore"):
        for entry in (ROOT / name).read_text().split():
            token = entry.strip("/").removeprefix("**/")
            assert not (token == "seeds" or token.startswith("seeds/")), f"{name} excludes seeds/ as {entry!r}"


def test_the_dockerfile_states_the_real_size_of_the_seed_payload():
    """The COPY's comment is what the next person sizing the image reads, and it claimed ~15 MB
    for 3.6 (L4 review M2). A drift test rather than a constant: change the photographs and this
    is what tells you the comment did not move with them."""
    mib = sum(f.stat().st_size for f in (ROOT / "seeds").rglob("*") if f.is_file()) / (1024 * 1024)
    assert f"~{mib:.1f} MB" in (ROOT / "Dockerfile").read_text(), f"seeds/ is {mib:.2f} MiB; the Dockerfile comment disagrees"
