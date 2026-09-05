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
    assert cfg["deploy"]["preDeployCommand"] == "python scripts/migrate.py"
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
