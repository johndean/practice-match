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

# Fix round 1's frontend-coverage ruling (John, 2026-09-06) plus the app.setup.js addition
# ratified in fix round 2 — the exact set frontend/vite.config.ts's coverage.exclude must carry.
RATIFIED_COVERAGE_EXCLUDE = {
    "src/App.vue",
    "src/app.setup.js",
    "src/logic.js",
    "src/dc-logic.js",
    "src/generated/**",
    "src/lib/**",
    "src/map/engine.ts",
    "src/map/testing/**",
    "src/**/*.test.ts",
    "src/**/*.d.ts",
}


def _strip_line_comments(block: str) -> str:
    # A `//` comment inside the exclude array can itself contain an apostrophe (e.g. "App.vue's
    # <script setup>"), which would otherwise be misread as a string delimiter by the naive
    # quote-matching regex below.
    return "\n".join(line for line in block.splitlines() if not line.strip().startswith("//"))


def _vite_coverage_config() -> tuple[dict[str, int], set[str]]:
    text = (ROOT / "frontend" / "vite.config.ts").read_text()
    thresholds_block = re.search(r"thresholds:\s*\{([^}]*)\}", text)
    assert thresholds_block, "frontend/vite.config.ts: coverage.thresholds block not found"
    thresholds = {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", thresholds_block.group(1))}
    exclude_block = re.search(r"exclude:\s*\[(.*?)\]", text, re.DOTALL)
    assert exclude_block, "frontend/vite.config.ts: coverage.exclude block not found"
    exclude = set(re.findall(r"'([^']*)'", _strip_line_comments(exclude_block.group(1))))
    return thresholds, exclude


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
    lint = ruff.get("lint", {})
    # Checked independently at BOTH levels (fix round 3 hardening): ruff honours an ignore
    # wherever it's written, so checking only [tool.ruff.lint] would miss one hiding in the
    # top-level [tool.ruff] table even while [tool.ruff.lint] also exists.
    for scope, table in (("[tool.ruff]", ruff), ("[tool.ruff.lint]", lint)):
        assert not table.get("ignore"), f"{scope} must carry no ignore"
        assert not table.get("extend-ignore"), f"{scope} must carry no extend-ignore"
        assert not table.get("per-file-ignores"), f"{scope} must carry no per-file-ignores"
    extend_select = set(lint.get("extend-select", []))
    assert {"I", "RUF"} <= extend_select, "[tool.ruff.lint] extend-select must include I and RUF"


def test_frontend_coverage_thresholds_are_100_and_exclude_is_the_ratified_set():
    thresholds, exclude = _vite_coverage_config()
    assert thresholds == {"lines": 100, "branches": 100, "functions": 100, "statements": 100}
    assert exclude == RATIFIED_COVERAGE_EXCLUDE


def test_policy_doc_ruff_paths_match_the_ci_workflow():
    policy = (ROOT / "docs" / "superpowers" / "specs" / "2026-09-05-quality-and-performance-policy.md").read_text()
    workflow = (ROOT / ".github" / "workflows" / "quality.yml").read_text()
    policy_m = re.search(r"poetry run ruff check ([\w/ ]+?)(?:`|&&)", policy)
    workflow_m = re.search(r"poetry run ruff check ([\w/ ]+?)(?:\n|$)", workflow)
    assert policy_m, "no `poetry run ruff check ...` invocation found in the policy doc"
    assert workflow_m, "no `poetry run ruff check ...` step found in quality.yml"
    assert policy_m.group(1).strip() == workflow_m.group(1).strip()


def test_working_docs_carry_the_railway_status_rule_and_the_key_handling_rule():
    for name in ("CLAUDE.md", "DEPLOY.md"):
        text = (ROOT / name).read_text()
        assert "railway status" in text and "Project: Practice Match" in text, name
        assert "CENSUS_API_KEY" in text and "never" in text.lower(), name


def test_deploy_md_carries_the_skip_verify_rule():
    text = (ROOT / "DEPLOY.md").read_text()
    assert "SKIP_VERIFY" in text
    assert "must never be habitual" in text


def test_perf_workflow_targets_qa_with_thresholds():
    """Policy §3's nightly load smoke: the workflow and the k6 script must keep pointing at
    QA and keep the budgets that make the run a gate rather than a report."""
    workflow = ROOT / ".github" / "workflows" / "perf.yml"
    assert workflow.exists(), "the nightly load smoke workflow is missing"
    text = workflow.read_text()
    wf = yaml.safe_load(text)
    # `on:` is YAML 1.1's boolean True once parsed, which is why it is looked up as a key
    # rather than the string "on".
    triggers = wf[True]
    assert triggers["schedule"] == [{"cron": "0 6 * * *"}], triggers
    assert "workflow_dispatch" in triggers, "the run must be launchable by hand (gh workflow run)"
    for name, job in wf["jobs"].items():
        assert "timeout-minutes" in job, name
    assert "qa.foundation.vin" in text, "the load smoke must run against QA, never production"
    # Enumerate every host-like token ending in the domain and require them ALL to be QA's.
    # Two weaker forms were tried and each let a production target through (fix rounds 1 and 2):
    # the literal `"foundation.vin/api"`, which a bare `BASE_URL: https://<host>` can never
    # contain whatever host it names; and `re.search(r"(?<!qa\.)\bfoundation\.vin\b", text)`,
    # which is case-sensitive (`https://FOUNDATION.VIN` slipped past) and whose lookbehind is
    # un-anchored (`notqa.foundation.vin` slipped past too). Collecting the hosts instead of
    # hunting for a bad one means anything that is not exactly qa.foundation.vin fails, and the
    # message names the offender.
    hosts = {h.lower() for h in re.findall(r"[\w.-]*foundation\.vin", text, re.IGNORECASE)}
    assert hosts == {"qa.foundation.vin"}, f"production must not be a target: {sorted(hosts)}"
    # The member token is a GitHub Actions secret John sets; it must never become a literal.
    assert "${{ secrets.MEMBER_TOKEN }}" in text
    assert "scripts/k6-smoke.js" in text

    k6 = (ROOT / "scripts" / "k6-smoke.js").read_text()
    assert "p(95)<400" in k6, "the p95 budget (policy §3) is gone"
    assert "rate==0" in k6, "the zero-error-rate budget (policy §3) is gone"


def test_deploy_md_documents_the_site_mode_matrix():
    text = (ROOT / "DEPLOY.md").read_text()
    assert "SITE_MODE" in text and "coming_soon" in text
    assert "never goes to QA" in text
    for name in ("CLAUDE.md",):
        assert "SITE_MODE" in (ROOT / name).read_text(), name


def test_deploy_md_documents_the_expect_sha_semantics():
    """verify-deploy.sh's `${EXPECT_SHA:-…}` treats unset and empty identically, so the
    runbook must not tell an operator that blanking it disables the check."""
    text = (ROOT / "DEPLOY.md").read_text()
    assert "EXPECT_SHA" in text
    lowered = text.lower()
    assert "unset or empty" in lowered, "the unset-equals-empty rule is undocumented"
    assert "outside a git checkout" in lowered, "the only skip condition is undocumented"
    for wrong in ("disables the check", "disable the check"):
        assert wrong not in lowered, f"DEPLOY.md repeats the wrong EXPECT_SHA semantics: {wrong!r}"
