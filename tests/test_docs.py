import json
import re
import tomllib
from pathlib import Path
from typing import cast

import pytest
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
    "scripts/bootstrap_admin.py scripts/seed_persona.py --strict",
    "poetry run pytest -q -W error",
    # I5 fix round 1, C1 (John, 2026-09-07): `scripts/` joins the gate. The one arm that kept it
    # below 100 % — `scripts/migrate.py`'s `__main__` guard — is now covered by
    # `tests/test_migrate.py::test_cli_entrypoint_runs_main_when_executed_as___main__`.
    # P14 C4 (2026-09-07) then raised main's own gate to the same 100 % app+scripts BRANCH gate
    # (it had been `--cov=app --cov-fail-under=90` while two pre-existing gaps stood open:
    # app/db.py's other-loop disposal arm and scripts/migrate.py's `__main__` guard). Both are
    # covered now, so nothing has to be relaxed to keep it green. Asserted as one joined
    # substring — the stricter of the two forms the merge inherited, since it also pins the
    # flags' order and adjacency in quality.yml.
    "--cov=app --cov=scripts --cov-branch",
    "--cov-report=xml",
    "--cov-fail-under=100",
    "bash tests/scripts/test_start_sh.sh",
    "bash tests/scripts/test_verify_image_sh.sh",
    "bash tests/scripts/test_deploy_guard.sh",
    "bash tests/scripts/test_deploy_archive.sh",
    "bash tests/scripts/test_verify_deploy.sh",
    "bash tests/scripts/test_bootstrap_admin.sh",
    "diff-cover coverage.xml --compare-branch=origin/main --fail-under=100",
    "npx vue-tsc --noEmit",
    "npm run build",
    "npx vitest run --coverage",
    "npx playwright test",
    "--project=coming-soon-reference",
    "--project=coming-soon\n",
)

# Fix round 1, item 1: the tools quality.yml runs must be tracked dependencies, not installed
# ad hoc inside the job.
FORBIDDEN_CI_SUBSTRINGS = ("pip install", "npm install --no-save", "--cov-fail-under=9")

# Fix round 1's frontend-coverage ruling (John, 2026-09-06) plus the app.setup.js addition
# ratified in fix round 2 — the exact set frontend/vite.config.ts's coverage.exclude must carry.
# Re-ratified 2026-09-07 (F1): the two hand-written files are measured. `src/dc-logic.js` (the
# 13-line React-shaped base class every setState runs through) and `src/lib/**` (a hand-written
# Leaflet loader) were the only entries in this set that were neither generated from the design
# nor verbatim-ported, and they were listed solely because the set was ratified. Browse V3's
# final-review fix round gave both behaviour tests (src/dc-logic.test.ts, src/lib/leaflet.test.ts)
# and re-derived that both measure 100/100/100/100 unexcluded, but could not drop them here
# because this pin is John's and no file under tests/ changed on that branch. Every remaining
# entry is unchanged: what stays out is generated, verbatim-ported, types-only or a test double.
RATIFIED_COVERAGE_EXCLUDE = {
    "src/App.vue",
    "src/app.setup.js",
    "src/logic.js",
    "src/generated/**",
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
    assert {"gitleaks", "backend", "frontend", "coming-soon"} <= set(wf["jobs"])
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
    data = tomllib.loads((ROOT / ".gitleaks.toml").read_text())
    paths = data["allowlist"]["paths"]
    assert "(?i)^docs/.*" not in paths
    assert "(?i)^tests/.*" not in paths
    assert "(?i)^frontend/tests/.*" not in paths  # M-7: the broad frontend/tests allowlist is gone too
    assert "(?i)^docs/design-reference/.*" in paths


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
    # No member token until Sub-project 2 restores the four-endpoint list (John, 2026-09-06).
    assert "MEMBER_TOKEN" not in text, "no member token until Sub-project 2 restores the four-endpoint list (John, 2026-09-06)"
    assert "scripts/k6-smoke.js" in text

    k6 = (ROOT / "scripts" / "k6-smoke.js").read_text()
    assert "p(95)<400" in k6, "the p95 budget (policy §3) is gone"
    assert "rate==0" in k6, "the zero-error-rate budget (policy §3) is gone"
    assert re.search(r"for \(const p of \['/api/healthz'\]\)", k6), "until SP2 the nightly hits only the health endpoint (John, 2026-09-06)"
    assert "MEMBER_TOKEN" not in k6
    policy = (ROOT / "docs" / "superpowers" / "specs" / "2026-09-05-quality-and-performance-policy.md").read_text()
    block = re.search(r"`scripts/k6-smoke.js`:\n+```js\n(.*?)```", policy, re.DOTALL)
    assert block and block.group(1) == k6, "the policy's §5 block and scripts/k6-smoke.js must stay byte-identical"


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


def test_deploy_md_documents_the_coming_soon_verify_output():
    """verify-deploy.sh is site-mode aware (Task 11f): production's coming-soon shell and
    /api/interest probe replace the SPA fallback check, and the runbook must say so."""
    text = (ROOT / "DEPLOY.md").read_text()
    assert "coming-soon shell OK" in text
    assert "interest endpoint OK" in text
    assert "site_mode coming_soon" in text


def test_deploy_md_says_the_api_container_runs_migrations_at_start():
    text = (ROOT / "DEPLOY.md").read_text()
    assert "runs the migrations at start" in text
    assert "Deploy aborted by the pre-deploy hook" not in text  # the old rollback row's claim was never true on Railway
    assert "unreachable at boot" in text
    assert "keeps serving" not in text


def test_deploy_md_records_the_forwarded_for_rule_and_its_probe():
    text = (ROOT / "DEPLOY.md").read_text()
    assert "first X-Forwarded-For hop" in text
    assert "203.0.113" in text  # the probe recipe
    assert "anything other than" in text
    assert "198.51.100" in text  # the second pass
    assert "30/day" in text  # OBS-7


def test_deploy_md_documents_expect_site_mode():
    """I2: deploy.sh runs verify-deploy.sh itself (scripts/deploy.sh:26), so the launch flip must
    prefix EXPECT_SITE_MODE=app onto `scripts/deploy.sh production` — prefixing verify-deploy.sh alone
    would still fail at deploy.sh's own internal verification step first."""
    text = (ROOT / "DEPLOY.md").read_text()
    assert "EXPECT_SITE_MODE=app scripts/deploy.sh production" in text
    assert "EXPECT_SITE_MODE=app scripts/verify-deploy.sh production" not in text


def test_public_indexing_row_matches_the_site_mode_matrix():
    text = (ROOT / "DEPLOY.md").read_text()
    row = next(line for line in text.splitlines() if line.startswith("| `PUBLIC_INDEXING`"))
    assert "`true` on production" in row and "noindex" in row
    assert "flip to true at launch" not in (ROOT / ".env.example").read_text()
    assert "flip to true at launch" not in (ROOT / "app" / "config.py").read_text()


def test_claude_md_lists_variable_names_only():
    text = (ROOT / "CLAUDE.md").read_text()
    assert "sed -E 's/(SECRET|KEY|URL)=.*/" not in text  # matched nothing on CLI 5.x's table output; values were printed
    assert "railway variable list --service api --environment QA --json" in text


def test_deploy_md_records_the_nightly_load_smoke_baseline():
    """Task 10c follow-up: the first manual run of the nightly load smoke (from main) is recorded
    so later runs can be compared against a number, not a memory."""
    text = (ROOT / "DEPLOY.md").read_text()
    assert "Nightly load smoke baseline" in text
    assert "p95" in text and "2026-09-06" in text


def test_reference_server_serves_the_coming_soon_design():
    assert (ROOT / "docs" / "design-reference" / "coming-soon" / "Coming Soon.dc.html").exists()
    assert "docs/design-reference/coming-soon" in (ROOT / "frontend" / "tests" / "reference-server.mjs").read_text()


def test_deploy_md_documents_automation_tokens_and_their_two_exceptions():
    """Task I5b (controller ruling, 2026-09-07 — concern 2). An `api_token` may now carry `staff`
    or `admin`, so the operator page has to say who mints one and — the part that makes a standing
    administrative bearer safe to hand out — the two things it can never do."""
    text = (ROOT / "DEPLOY.md").read_text()
    assert "## Automation tokens" in text
    assert "POST /api/admin/tokens" in text and "Bearer pm_<id>.<secret>" in text
    assert "90 days" in text
    assert "re-authenticate" in text and "manage tokens" in text
    assert "/api/admin/tokens/{id}/revoke" in text
    # I5b review M1: removing a staff/admin grant revokes the tokens that account may no longer
    # mint, so the page must not leave an operator thinking they have to hunt them down by hand.
    assert "grant_removed" in text


def test_deploy_md_says_an_applied_migration_is_immutable():
    """Task I5c (controller ruling, 2026-09-07 — concern 6). `scripts/migrate.py` records each
    file's SHA-256 from f3b7d41 and refuses to run when an applied file has changed, so the
    operator page has to say what exit 4 means and what to do about it — the alternative is
    learning it from a container that will not start."""
    text = (ROOT / "DEPLOY.md").read_text()
    assert "An applied migration is immutable" in text
    assert "SHA-256" in text and "exit 4" in text
    assert "drop and recreate the database or restore the file" in text
    # ...and that no persistent environment is affected today: QA and production predate Wave 2a.
    assert "b9d01ad" in text
    # Fix round 1, L4: the guarantee is not retroactive — a row applied before f3b7d41 carries no
    # checksum and is never checked, so `001`/`002` on QA and production stay silently mutable.
    assert "Enforcement begins with the files applied from `f3b7d41` onward" in text
    assert "carry no checksum and are not checked" in text
    assert "001_init.sql" in text


def test_dockerfile_copies_the_build_sha_stamp_with_the_optional_glob_form():
    """P14: /app/BUILD_SHA is what /api/healthz reports as commit_sha, and scripts/deploy.sh
    writes it into the archive it uploads. A build whose context has no stamp (a local
    `scripts/verify-image.sh`, or a git-connected Railway build) must still succeed, so the
    source is the `BUILD_SH[A]` glob — but a COPY whose ONLY source matches nothing fails
    outright ("COPY failed: no source files were specified", measured against the local
    daemon 2026-09-07), so the glob must stay paired with a source that is always present."""
    text = (ROOT / "Dockerfile").read_text()
    copies = [ln for ln in text.splitlines() if ln.startswith("COPY") and "BUILD_SH" in ln]
    assert copies, "the Dockerfile must copy BUILD_SHA using the optional-glob form BUILD_SH[A]"
    for line in copies:
        assert re.fullmatch(r"COPY \S+ BUILD_SH\[A\] \./", line), (
            f"the optional glob must be paired with an always-present source: {line!r}"
        )


def test_deploy_md_documents_the_archive_upload_and_the_new_exit_codes():
    """P14: the deploy path can no longer ship a tree other than the one it names. The
    runbook has to say what is uploaded, how a branch is deployed, and what the two new
    refusals mean — an operator who hits 66 or 67 must not have to read the script."""
    text = (ROOT / "DEPLOY.md").read_text()
    assert "git archive" in text, "the archive-based upload is undocumented"
    assert "scripts/deploy.sh QA .worktrees/<branch>" in text, "the SOURCE_DIR usage is undocumented"
    assert "pointer file" in text, "the worktree hazard that caused P14 is unrecorded"
    assert "exit 66" in text and "exit 67" in text, "the new exit codes are undocumented"
    # C2: a `railway up` that fails at upload time creates no deployment, so the previous
    # deploy stays the newest and a status-only poll would read its SUCCESS as this one's.
    assert "upload did not create a deployment" in text, "the fail-closed upload guard is undocumented"
    assert "strictly newer" in text, "the createdAt baseline rule is undocumented"
    assert "EXPECT_VERSION" in text, "the verifier's artefact check is undocumented"
    # M2: the verifier's defaults are its own checkout's, so a hand-run after a SOURCE_DIR
    # deploy needs both knobs passed explicitly or it fails a perfectly good deploy.
    assert "EXPECT_SHA=<sha> EXPECT_VERSION=<version> scripts/verify-deploy.sh QA" in text, (
        "the ready-to-paste re-verify line for a SOURCE_DIR deploy is undocumented"
    )


def test_claude_md_traffic_light_block_records_the_archive_upload():
    """The 🚦 block is the one place every assistant reads before touching Railway."""
    text = (ROOT / "CLAUDE.md").read_text()
    assert (
        "deploy.sh uploads a `git archive` of the source's HEAD, never the working directory; "
        "a linked worktree must be passed as SOURCE_DIR" in text
    )


def test_platform_plan_records_the_p14_hotfix():
    text = (ROOT / "docs" / "superpowers" / "plans" / "2026-09-05-practice-match-platform.md").read_text()
    assert "### Task 14: Deploy what is committed, verify what is deployed (hotfix, 2026-09-07)" in text
    assert "--path-as-root" in text, "the flag that makes the upload path the archive root is unrecorded"
    assert "BUILD_SHA" in text, "the artefact stamp is unrecorded"


def test_claude_md_local_backend_gate_is_the_one_ci_runs():
    """P14 C4: the backend gate is the 100 % app+scripts branch gate. The command in
    CLAUDE.md's Common operations must be the one CI runs verbatim — otherwise the loop
    John actually types is weaker than the gate, and the first he hears of it is a red CI."""
    claude = (ROOT / "CLAUDE.md").read_text()
    workflow = (ROOT / ".github" / "workflows" / "quality.yml").read_text()
    policy = (ROOT / "docs" / "superpowers" / "specs" / "2026-09-05-quality-and-performance-policy.md").read_text()
    gate = "poetry run pytest -q -W error --cov=app --cov=scripts --cov-branch"
    assert gate in claude, "CLAUDE.md's Common operations must carry the backend gate verbatim"
    assert gate in workflow, "quality.yml must run the same gate"
    assert gate in policy, "the quality policy must state the same gate"
    for doc, text in (("CLAUDE.md", claude), ("quality.yml", workflow), ("the quality policy", policy)):
        assert "--cov-fail-under=100" in text, doc
        assert "--cov-fail-under=90" not in text, f"{doc} still carries the old 90 % threshold"


# The four sub-project plans whose policy-summary line quoted the backend CI gate. P14 raised
# it, so each has to quote the raised one — a plan that still says 90 % is an instruction to
# lower the gate the next time someone executes it (the shape of review finding L9).
PLANS_QUOTING_THE_BACKEND_GATE = (
    "2026-09-05-practice-match-map-engines.md",
    "2026-09-05-practice-match-google-maps-greenfield.md",
    "2026-09-05-practice-match-identity-access-email.md",
    "2026-09-05-practice-match-census-data-layer.md",
)


def test_sub_project_plans_quote_the_raised_backend_gate():
    """P14 fix round 1, L9 extended: `main` is the canonical copy of every plan, and each of
    these opens by summarising the quality policy's CI gates. Left at the old 90 % floor they
    would walk a future implementer straight into lowering it — and `tests/test_docs.py`
    already makes that a RED test, so the conflict would surface as a mystery failure rather
    than as the instruction it is."""
    for name in PLANS_QUOTING_THE_BACKEND_GATE:
        text = (ROOT / "docs" / "superpowers" / "plans" / name).read_text()
        assert "pytest -W error --cov=app --cov=scripts --cov-branch --cov-fail-under=100" in text, name
        assert "raised by P14, 2026-09-07" in text, f"{name} must date the raise"
        assert "--cov-fail-under=90" not in text, f"{name} still quotes the old 90 % floor"


def test_claude_md_gate_includes_the_dom_oracle():
    """Final review M2 (2026-09-07). Option A made the DOM oracle THE proof of zero regression
    for the thirteen non-Browse screens (CLAUDE.md's own "Source of truth" paragraph says so),
    and it runs under neither `npm run test:smoke` nor `npm run test:visual` — only under
    `npm run test:e2e`, whose `--project=app` matches visual|smoke|dom. CI runs it; an operator
    following CLAUDE.md's four-item gate by hand did not."""
    text = (ROOT / "CLAUDE.md").read_text()
    gate = next(line for line in text.splitlines() if line.startswith("- **Verification gate"))
    assert "npm run test:visual:baselines" in gate, "the hand-run gate does not regenerate the oracles first"
    assert "npm run test:e2e" in gate, "the hand-run gate still skips the DOM oracle"
    scripts = json.loads((ROOT / "frontend" / "package.json").read_text())["scripts"]
    assert "--project=app" in scripts["test:e2e"], scripts["test:e2e"]
    # …and no spec filter, or it would not be all three suites.
    assert "spec.ts" not in scripts["test:e2e"], scripts["test:e2e"]
    # `in`, not `startswith`: A-I7.2 prefixes the e2e line with `docker compose … up -d &&`,
    # because the `app` project now starts the real API against the compose Postgres/Redis. The
    # assertion is unchanged — the block must still run the DOM oracle, not the pixel gate alone.
    ops = [line for line in text.splitlines() if "cd frontend &&" in line and "test:" in line]
    assert any("npm run test:e2e" in line for line in ops), "the Common operations block still runs the pixel gate alone"
    assert any("docker compose -f docker-compose.dev.yml up -d" in line for line in ops), (
        "the Common operations e2e line no longer starts the compose Postgres/Redis the app project's API needs"
    )


# The two plan sites that print the coverage-exclusion list as prose. Both are historical
# records rather than live instructions, but an implementer reading either would be told the
# old set — the same drift class as the backend-gate lines (L9).
PLANS_QUOTING_THE_COVERAGE_EXCLUSIONS = (
    "2026-09-06-browse-v3-mobile.md",
    "2026-09-05-practice-match-platform.md",
)
F1_NOTE = (
    "(Re-ratified 2026-09-07, F1: `src/dc-logic.js` and `src/lib/**` left the exclusion list "
    "once their tests landed; every hand-written file under `src/**` is measured at 100 %, so "
    "the set grows with the code — 14 files when F1 landed on main.)"
)


def test_plans_that_print_the_coverage_exclusions_carry_the_f1_note():
    """F1: `src/dc-logic.js` and `src/lib/**` are measured now, so every place that prints the
    old list has to say so beside it — Browse V3's Global Constraint (g), which is the reason
    that branch could not widen the set, and Task 12's configuration step, which set it."""
    for name in PLANS_QUOTING_THE_COVERAGE_EXCLUSIONS:
        text = (ROOT / "docs" / "superpowers" / "plans" / name).read_text()
        assert "'src/dc-logic.js'" in text or "`src/dc-logic.js`" in text, f"{name}: expected the exclusion list here"
        assert F1_NOTE in text, f"{name} prints the old exclusion list without the F1 re-ratification note"


def test_the_playwright_persona_password_default_matches_seed_persona():
    """A-I7: `frontend/tests/harness.ts` signs the Playwright `app` project in as the design
    persona with `PERSONA_PASSWORD` or the default below; `scripts/seed_persona.py` writes the
    Argon2id hash of `PERSONA_PASSWORD` or ITS default. They are one documented test-only
    constant in two languages, and if they drift every `app`-project run answers 401 at a point
    far from the cause — so they are pinned equal here, where the failure names the two files."""
    seeded = re.search(r'^DEFAULT_PASSWORD = "([^"]+)"', (ROOT / "scripts" / "seed_persona.py").read_text(), re.MULTILINE)
    presented = re.search(r"^export const PERSONA_DEFAULT_PASSWORD = '([^']+)';",
                          (ROOT / "frontend" / "tests" / "harness.ts").read_text(), re.MULTILINE)
    assert seeded, "scripts/seed_persona.py no longer defines DEFAULT_PASSWORD"
    assert presented, "frontend/tests/harness.ts no longer defines PERSONA_DEFAULT_PASSWORD"
    assert presented.group(1) == seeded.group(1)


def test_claude_md_does_not_claim_v2_byte_identity_after_the_launch_removal():
    """Review round 1, I3. Two sentences in CLAUDE.md outlived their truth: the thirteen non-Browse
    screens WERE byte-identical to V2 from Task V13 until Task I8a's launch removal (A6, ruled
    D-I8-6) took the prototype jump bar off the top of every screen, and `baseline-manifest.json`
    held the V1-era V2 hashes until the same commit re-froze it. Nothing pinned either, so both
    went stale silently — which is the whole failure mode this file exists to prevent.

    V2 itself is unaffected: it remains the pre-V3 oracle a suspected regression is diffed
    against, which is a different job from being what the gates compare to."""
    text = (ROOT / "CLAUDE.md").read_text()
    assert "byte-identical to V2 again, hashes and all, **until the launch removal**" in text, (
        "CLAUDE.md must date the V2 byte-identity claim to before the launch removal"
    )
    assert "V1-era V2 hashes" not in text, "CLAUDE.md still says the manifest holds the V1-era V2 hashes"
    assert "post-launch-removal hashes" in text, "CLAUDE.md does not say what the manifest holds now"
    assert "D-I8-6" in text, "the ruling that moved the baselines is not cited"
    # …and the gate line, which made the same claim without a date.
    gate = next(line for line in text.splitlines() if line.startswith("- **Verification gate"))
    assert "until the launch removal" in gate, gate
    # V2's actual job survives.
    assert "remains the **pre-V3 oracle**" in text


def test_claude_md_counts_the_five_prototype_props_and_says_which_are_read():
    """Review round 1, M5. The launch-removal section said "the four prototype props" after A5.7
    added a fifth, and described `prototypeBar` as one of the reference's ways into a state — but
    A6.4b removed the only expression that ever read it, so it is declared for the parity check in
    `app-generated.test.ts` and for nothing else."""
    text = (ROOT / "CLAUDE.md").read_text()
    assert "All five prototype props stay **declared**" in text
    assert "the four prototype props" not in text
    assert "`prototypeBar` is declared for that parity check alone" in text
    # The five, by name, in the section that lists them.
    section = text.split("## Launch-removal list")[1]
    for prop in ("prototypeBar", "startScreen", "startViewport", "startGate", "me"):
        assert f"`{prop}`" in section, prop


def _harness_personas() -> dict[str, dict[str, object]]:
    """`frontend/tests/harness.ts`'s `PERSONAS`, read without a TypeScript parser.

    Each entry is written as ONE line precisely so this pin can read it; the file says so beside
    them. The strings are what the reference is handed through the `me` prototype prop (A5.7) and
    therefore what the design's own header renders on the oracle."""
    source = (ROOT / "frontend" / "tests" / "harness.ts").read_text()
    pattern = (r"^  (\w+): \{ email: '([^']+)', name: '([^']+)', role: '([^']+)', "
               r"initials: '([^']+)', state: '([^']+)', roles: \[([^\]]*)\] \},?$")
    found: dict[str, dict[str, object]] = {}
    for m in re.finditer(pattern, source, re.MULTILINE):
        key, email, name, role, initials, state, roles = m.groups()
        found[key] = {"email": email, "name": name, "role": role, "initials": initials, "state": state,
                      "roles": tuple(r.strip().strip("'") for r in roles.split(",") if r.strip())}
    assert len(found) == 6, f"expected the six harness personas as one line each, read {sorted(found)}"
    return found


def test_the_harness_personas_are_the_accounts_seed_persona_seeds_with_the_labels_the_api_computes():
    """A-I8.2 / D-I8-8: the visual oracle's personas are ONE fact in two languages.

    Since amendment A5.4 the account menu renders `/api/me`'s computed `role` and `initials`
    (spec §4, `app/api/auth.py::me_payload`), and `app.auth.labels` derives both from the account's
    grants and display name. The harness holds each persona's payload as a constant, because the
    REFERENCE is handed it through the `me` prototype prop (A5.7) — so if these strings and
    `labels.py` ever disagree, the reference and the app render different headers and every
    member-screen baseline is wrong. Pinned per persona, and the drift can come from either side."""
    from app.auth.labels import initials, role_label
    from scripts import seed_persona

    seeded_roles: dict[str, tuple[str, ...]] = {
        seed_persona.PERSONA_EMAIL: seed_persona.PERSONA_ROLES,
        **{email: roles for email, roles in seed_persona.ORACLE_PERSONAS},
        **{email: () for email, _state, _name in seed_persona.STATE_PERSONAS},
    }
    seeded_names: dict[str, str] = {
        seed_persona.PERSONA_EMAIL: seed_persona.PERSONA_NAME,
        **{email: seed_persona.PERSONA_NAME for email, _roles in seed_persona.ORACLE_PERSONAS},
        **{email: name for email, _state, name in seed_persona.STATE_PERSONAS},
    }
    # Only the three members carry an affiliation; an applicant has none to confirm yet, which is
    # rather the point for `declined@`.
    members = {seed_persona.PERSONA_EMAIL, *(email for email, _roles in seed_persona.ORACLE_PERSONAS)}
    seeded_states: dict[str, str] = {email: state for email, state, _name in seed_persona.STATE_PERSONAS}

    for key, persona in _harness_personas().items():
        email = str(persona["email"])
        assert email in seeded_roles, f"{key} names {email}, which scripts/seed_persona.py does not seed"
        assert persona["roles"] == tuple(sorted(seeded_roles[email])), (key, persona["roles"])
        assert persona["name"] == seeded_names[email], (key, persona["name"])
        assert persona["state"] == seeded_states.get(email, "active"), (key, persona["state"])
        affiliation = seed_persona.PERSONA_AFFILIATION if email in members else None
        assert persona["role"] == role_label(frozenset(seeded_roles[email]), affiliation), (key, persona["role"])
        assert persona["initials"] == initials(seeded_names[email]), (key, persona["initials"])


def test_the_buyer_persona_reproduces_the_design_fixture_label_letter_for_letter():
    """A-I8.2, the invariant the nineteen buyer-family baselines rest on.

    John's rule for this wave is that the approved design's copy does not change, so the oracle
    persona was chosen to fit the design: `labels.role_label({"buyer"}, "StartUp Club")` must
    reproduce `logic.js`'s fixture `state.me.role` exactly, or the reference and the app disagree on
    the header of every buyer-family state and nineteen baselines move that should not."""
    from app.auth.labels import initials, role_label
    from scripts import seed_persona

    design = (ROOT / "docs" / "design-reference" / "design_handoff_practice_match_v3" / "Practice Match V3.dc.html").read_text()
    match = re.search(r'^    me: \{ name: "([^"]+)", role: "([^"]+)", initials: "([^"]+)" \}$', design, re.MULTILINE)
    assert match, "the design's fixture persona is no longer the single line this pin reads"
    name, role, inits = match.groups()

    buyer_roles = dict(seed_persona.ORACLE_PERSONAS)["buyer@practice-match.test"]
    assert role == role_label(frozenset(buyer_roles), seed_persona.PERSONA_AFFILIATION), role
    assert name == seed_persona.PERSONA_NAME, name
    assert inits == initials(seed_persona.PERSONA_NAME), inits
    # And the harness must be handing that same account to the buyer-family states.
    assert _harness_personas()["buyer"]["role"] == role


def _users_ts_literal(name: str) -> object:
    """One of the three exported JSON literals in `frontend/src/admin/users.ts`.

    They are written as JSON on one line each precisely so this test can read them without a
    TypeScript parser; the file says so beside them."""
    source = (ROOT / "frontend" / "src" / "admin" / "users.ts").read_text()
    match = re.search(rf"^export const {name}(?:: [^=]+)? = (.+);$", source, re.MULTILINE)
    assert match, (
        f"frontend/src/admin/users.ts: {name} is not a single-line exported literal, so this "
        f"cross-language pin cannot read it. Each of NOTE_REQUIRED, ACTIONS and PILLS is written "
        f"as double-quoted JSON on ONE line for exactly that reason; the file says so beside them."
    )
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        # Outside the `except`, so the failure is ONE named line rather than a chained
        # JSONDecodeError naming a column in a string nobody can see from here (re-review).
        reason = str(exc)
    pytest.fail(
        f"frontend/src/admin/users.ts: {name} is no longer DOUBLE-QUOTED JSON on a single line, "
        f"so this cross-language pin cannot read it ({reason}). Each of NOTE_REQUIRED, ACTIONS "
        f"and PILLS is written that way for exactly that reason; the file says so beside them. "
        f"Got: {match.group(1)[:120]}"
    )


def test_the_admin_users_tables_match_the_api():
    """Review Minor 3: the Admin Users table's three decision tables were hand-transcribed from
    `app/api/admin_users.py` with nothing watching them.

    A fifth note-required action added on the server would have left the UI POSTing a blank note
    and taking a 422 at click time; an action offered from a state `TRANSITIONS` refuses would
    have taken a 409 the same way; and an account state the API can report with no pill would
    have rendered its raw key. The design deliberately offers a SUBSET of the transitions (the
    API also allows `revoke` from five other states), so what is pinned is that the subset is
    legal — not that it is complete."""
    from app.api.admin_users import ACCOUNT_STATES, NOTE_REQUIRED, TRANSITIONS

    assert _users_ts_literal("NOTE_REQUIRED") == list(NOTE_REQUIRED)
    assert sorted(cast("dict[str, object]", _users_ts_literal("PILLS"))) == sorted(ACCOUNT_STATES)
    for state, offered in cast("dict[str, list[str]]", _users_ts_literal("ACTIONS")).items():
        for action in offered:
            assert action in TRANSITIONS, f"the Admin Users table offers {action!r}, which app/api/admin_users.py has no transition for"
            assert state in TRANSITIONS[action][0], f"the Admin Users table offers {action!r} from {state!r}, which the API refuses"
