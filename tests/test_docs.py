import re
import tomllib
from pathlib import Path

import yaml

from app.config import Settings

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "README.md", ROOT / "CLAUDE.md", ROOT / "DEPLOY.md", *sorted((ROOT / "docs").rglob("*.md"))]

# Extended per Task 9 policy §2 (docs/superpowers/specs/2026-09-05-quality-and-performance-policy.md)
# and Fix round 1 (2026-09-06): every one of these commands must appear verbatim (as a
# substring) in quality.yml. The scoped `--coverage.include=...`/`--coverage.thresholds.lines=85`
# flags and the standalone `npx vitest run tests/bundle-budget.test.ts` step from the first
# draft are gone — thresholds and scope now live in frontend/vite.config.ts's `test.coverage`
# (100/100/100/100), so the relaxed substring below is the one plain invocation that enforces
# them and already runs every test file (including bundle-budget.test.ts).
REQUIRED_CI_COMMANDS = (
    "poetry run ruff check app tests scripts",
    "poetry run mypy app --strict",
    "poetry run pytest -q -W error",
    "--cov=app",
    "--cov-report=xml",
    "--cov-fail-under=90",
    "bash tests/scripts/test_start_sh.sh",
    "bash tests/scripts/test_verify_image_sh.sh",
    "bash tests/scripts/test_deploy_guard.sh",
    "bash tests/scripts/test_verify_deploy.sh",
    "diff-cover coverage.xml --compare-branch=origin/main --fail-under=100",
    "npx vue-tsc --noEmit",
    "npm run build",
    "npx vitest run --coverage",
    "npx playwright test",
)

# Fix round 1, item 1: the tools quality.yml runs must be tracked dependencies, not installed
# ad hoc inside the job.
FORBIDDEN_CI_SUBSTRINGS = ("pip install", "npm install --no-save")


def env_names() -> set[str]:
    return {(f.alias or name).upper() for name, f in Settings.model_fields.items()}


def test_every_setting_is_documented_in_env_example_and_deploy_md():
    example = (ROOT / ".env.example").read_text()
    deploy = (ROOT / "DEPLOY.md").read_text()
    missing = sorted(n for n in env_names() if not re.search(rf"(?m)^#?\s*{n}=", example) or n not in deploy)
    assert missing == []


def test_relative_markdown_links_resolve():
    broken = []
    for doc in DOCS:
        text = doc.read_text(encoding="utf-8")
        # Fenced code blocks may contain regex/shell snippets that coincidentally look
        # like `](...)` (e.g. a JS character class `["'(](assets|ds)\/`); strip them
        # before scanning so only prose markdown links are checked.
        text = re.sub(r"(?s)```.*?```", "", text)
        for m in re.finditer(r"\]\(((?!https?://|#|mailto:)[^)\s]+)\)", text):
            target = (doc.parent / m.group(1).split("#")[0]).resolve()
            if not target.exists():
                broken.append(f"{doc.relative_to(ROOT)} -> {m.group(1)}")
    assert broken == []


def test_ci_workflow_runs_every_gate():
    path = ROOT / ".github" / "workflows" / "quality.yml"
    wf = yaml.safe_load(path.read_text())
    assert {"gitleaks", "backend", "frontend"} <= set(wf["jobs"])
    text = path.read_text()
    for cmd in REQUIRED_CI_COMMANDS:
        assert cmd in text, cmd


def test_ci_workflow_installs_no_ad_hoc_tooling():
    text = (ROOT / ".github" / "workflows" / "quality.yml").read_text()
    for forbidden in FORBIDDEN_CI_SUBSTRINGS:
        assert forbidden not in text, forbidden


def test_ci_workflow_jobs_have_a_timeout_and_the_backend_checkout_has_full_history():
    path = ROOT / ".github" / "workflows" / "quality.yml"
    wf = yaml.safe_load(path.read_text())
    for name, job in wf["jobs"].items():
        assert "timeout-minutes" in job, name
    backend_checkout = wf["jobs"]["backend"]["steps"][0]
    assert backend_checkout["uses"].startswith("actions/checkout")
    assert backend_checkout.get("with", {}).get("fetch-depth") == 0


def test_gitleaks_config_parses():
    tomllib.loads((ROOT / ".gitleaks.toml").read_text())


def test_ruff_config_selects_a_rule_set_with_no_ignores():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    ruff = pyproject.get("tool", {}).get("ruff")
    assert ruff, "pyproject.toml is missing [tool.ruff]"
    lint = ruff.get("lint", ruff)  # accept either [tool.ruff.lint] or top-level [tool.ruff]
    assert not lint.get("ignore") and not lint.get("extend-ignore"), "ruff config must carry no ignores (fix round 1)"


def test_working_docs_carry_the_railway_status_rule_and_the_key_handling_rule():
    for name in ("CLAUDE.md", "DEPLOY.md"):
        text = (ROOT / name).read_text()
        assert "railway status" in text and "Project: Practice Match" in text, name
        assert "CENSUS_API_KEY" in text and "never" in text.lower(), name


def test_deploy_md_carries_the_skip_verify_rule():
    text = (ROOT / "DEPLOY.md").read_text()
    assert "SKIP_VERIFY" in text
    assert "must never be habitual" in text
