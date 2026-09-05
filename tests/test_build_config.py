import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_dockerfile_declares_the_build_args_and_the_dispatcher_entrypoint():
    d = (ROOT / "Dockerfile").read_text()
    assert "ARG ENVIRONMENT=qa" in d and "ARG COMMIT_SHA=dev" in d
    assert 'ENTRYPOINT ["bash", "scripts/start.sh"]' in d and 'CMD ["api"]' in d


def test_railway_json_points_at_the_dispatcher_migrations_and_healthz():
    cfg = json.loads((ROOT / "railway.json").read_text())
    assert cfg["deploy"]["startCommand"] == "bash scripts/start.sh api"
    assert cfg["deploy"]["preDeployCommand"] == "python scripts/migrate.py"
    assert cfg["deploy"]["healthcheckPath"] == "/api/healthz"


def test_ignore_files_keep_secrets_tests_and_node_modules_out_of_uploads_and_images():
    for name in (".railwayignore", ".dockerignore"):
        text = (ROOT / name).read_text().split()
        for entry in ("frontend/node_modules", "tests", ".env", ".env.*"):
            assert entry in text, f"{name} lacks {entry}"
