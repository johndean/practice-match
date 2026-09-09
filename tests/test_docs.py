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
    # S5 review round 2: `scripts/reset_rate_limits.py` joins the list. The joined form pins the
    # flags' order and adjacency, so a new script has to be added here as well as to the workflow;
    # `test_ci_strict_mypy_covers_every_python_script` below is the rule that says WHICH scripts.
    # M2 (2026-09-08): the seed-listings scripts join the same line — the merged workflow runs the
    # union of both branches' scripts, and this pin is that union verbatim.
    "scripts/bootstrap_admin.py scripts/seed_persona.py scripts/reset_rate_limits.py scripts/prepare_photos.py scripts/seed_listings.py --strict",
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


def test_readme_describes_the_session_template_database():
    """Platform task P-TDB. The suite no longer migrates a database per test: it migrates one
    session template and clones it, and falls back to the old path when Postgres refuses to copy
    a template something is connected to. Both halves are operator-visible — a `pm_tmpl_*`
    database on the shared compose Postgres, and a warnings-summary line on a slow run — so the
    README section that tells someone how to run the suite has to say so. Pinned on the two
    strings that identify each half (the name pattern the fixture builds, and Postgres's own
    refusal text the fallback keys on), so the paragraph cannot be deleted or reworded away from
    what `tests/conftest.py` actually does."""
    text = (ROOT / "README.md").read_text()
    for phrase in ("pm_tmpl_", "TEMPLATE", "being accessed by other users"):
        assert phrase in text, f"README.md no longer describes the suite's template database: {phrase!r} is missing"


def test_ci_strict_mypy_covers_every_python_script():
    """S5 review round 2 (the implementer's own residual, ruled a gap): every `scripts/*.py` that
    CI measures for coverage must also be type-checked, and the file list is written out by hand in
    `quality.yml`.

    `scripts/reset_rate_limits.py` (A-S5.1) was added with tests and 100 % branch coverage but was
    never added to that hand-written list, so CI ran ruff and pytest over it and mypy over
    everything else — a gap nothing could see, because the only pin was a substring naming the
    three scripts that WERE listed. The rule is stated once here instead: the strict mypy step
    names every Python file under `scripts/`, so the next script is caught by this test rather than
    by a reviewer.

    Deliberately derived from the directory, not from a literal list — a list would have to be
    edited alongside the workflow, which is the failure mode this exists to prevent."""
    step = next(
        line for line in (ROOT / ".github" / "workflows" / "quality.yml").read_text().splitlines()
        if "mypy" in line and "--strict" in line and "scripts/" in line
    )
    missing = sorted(p.name for p in (ROOT / "scripts").glob("*.py") if f"scripts/{p.name}" not in step)
    assert missing == [], (
        f"{missing} are measured by CI's `--cov=scripts` but are not in its strict mypy step "
        f"({step.strip()}) — add them there, beside the others"
    )


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


def test_policy_p95_gate_reflects_the_re_measure_rule():
    """Task 15 (2026-09-08): `test_interest_stored_path_p95_within_budget` failed on a stalled
    shared runner while the identical commit passed everywhere else. The fix is `gate_p95`: every
    p95 gate measures once and, only if that first p95 is over budget, measures once more and
    asserts the second — both sample sets printed either way — so a regression still fails twice
    but a stalled runner does not. The policy row and the test module must both say so."""
    policy = (ROOT / "docs" / "superpowers" / "specs" / "2026-09-05-quality-and-performance-policy.md").read_text()
    assert ("when the first p95 is over budget the endpoint is measured once more and the second "
            "decides (a regression fails twice; a stalled shared runner does not), both sample sets "
            "printed") in policy
    latency = (ROOT / "tests" / "perf" / "test_api_latency.py").read_text()
    assert "from tests.perf.gate import gate_p95, p95_of" in latency, "test_api_latency.py must import gate_p95 from tests.perf.gate"


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


def test_the_harness_fixture_tokens_match_the_seed_scripts_pattern_and_the_three_new_state_emails():
    """Task S3/S5, same shape as the password pin above: `scripts/seed_persona.py`'s
    `FIXTURE_TOKENS` names the account and the `fixture-<purpose>-{n:02d}` pattern the visual
    harness (Task S5) mirrors as test-only constants, so the two never drift out of the one
    documented `fixture-<purpose>-NN` shape a raw token is ever allowed to look like.

    S3 shipped only the seed side and landed this as `xfail(strict=True)` so the branch stayed
    green; Task S5 added `FIXTURE_TOKEN_PREFIX`, `FIXTURE_TOKENS` and the three
    `*@practice-match.test` emails to `frontend/tests/harness.ts`, which turned the marker into an
    XPASS — S5's RED — and removing it is the GREEN."""
    from scripts import seed_persona

    assert seed_persona.FIXTURE_TOKENS == {
        # A-S5.2 (S-1): the verify tokens belong to `verify-me@`, the tenth account, because
        # consuming one confirms its account for good and the oracle needs `unverified@` to stay
        # unverified at every capture.
        "verify": ("verify-me@practice-match.test", "fixture-verify-{n:02d}"),
        "reset": ("verified@practice-match.test", "fixture-reset-{n:02d}"),
        "invite": ("invited@practice-match.test", "fixture-invite-{n:02d}"),
    }
    assert seed_persona.FIXTURE_TOKEN_PREFIX == "fixture-"

    harness = (ROOT / "frontend" / "tests" / "harness.ts").read_text()
    presented = re.search(r"^export const FIXTURE_TOKEN_PREFIX = '([^']+)';$", harness, re.MULTILINE)
    assert presented, "frontend/tests/harness.ts does not yet define FIXTURE_TOKEN_PREFIX (Task S5)"
    assert presented.group(1) == seed_persona.FIXTURE_TOKEN_PREFIX
    for email, _pattern in seed_persona.FIXTURE_TOKENS.values():
        assert email in harness, f"frontend/tests/harness.ts does not yet name {email} (Task S5)"

    # The harness builds each raw token from its own prefix table, so the two spellings of the
    # SAME twelve values are pinned equal rather than merely similar-looking.
    prefixes = re.search(r"^export const FIXTURE_TOKENS = \{ (.+) \} as const;$", harness, re.MULTILINE)
    assert prefixes, "frontend/tests/harness.ts no longer writes FIXTURE_TOKENS as one line"
    presented_prefixes = dict(re.findall(r"(\w+): '([^']+)'", prefixes.group(1)))
    count = re.search(r"^export const FIXTURE_TOKEN_COUNT = (\d+);$", harness, re.MULTILINE)
    assert count and int(count.group(1)) == seed_persona.FIXTURE_TOKEN_COUNT
    for purpose, (_email, pattern) in seed_persona.FIXTURE_TOKENS.items():
        for n in range(1, seed_persona.FIXTURE_TOKEN_COUNT + 1):
            assert pattern.format(n=n) == f"{presented_prefixes[purpose]}{n:02d}", (purpose, n)


def test_the_throwaway_address_shape_is_one_string_the_harness_and_the_seed_both_hold():
    """Task S7 fix round 1, ruling 4 (2026-09-08). The live sign-up and forgot flows create a real
    account per run at `e2e-<run>-<purpose>-<n>@example.org`, and `scripts/seed_persona.py`'s
    restoration now DELETES those accounts — so the shape it deletes by and the shape
    `frontend/tests/harness.ts`'s `throwawayEmail` produces must be one string, not two that look
    alike. A pattern that drifted wider than the addresses the harness makes would remove an
    account nobody meant it to; one that drifted narrower would silently stop cleaning up.

    Same shape as the fixture-token pin above: the seed owns the value, the harness mirrors it, and
    this is what keeps them equal."""
    from scripts import seed_persona

    harness = (ROOT / "frontend" / "tests" / "harness.ts").read_text()
    presented = re.search(r"^export const THROWAWAY_EMAIL_PATTERN = '([^']+)';$", harness, re.MULTILINE)
    assert presented, "frontend/tests/harness.ts does not define THROWAWAY_EMAIL_PATTERN (S7 fix round 1)"
    # The TS source escapes the backslash; the pattern itself is what both sides compile.
    assert presented.group(1).replace("\\\\", "\\") == seed_persona.THROWAWAY_EMAIL_PATTERN

    # …and it really is the shape the harness's own builder produces.
    builder = re.search(r"return `e2e-\$\{[^`]*\}@example\.org`;", harness)
    assert builder, "frontend/tests/harness.ts's throwawayEmail no longer builds e2e-…@example.org"
    assert re.match(seed_persona.THROWAWAY_EMAIL_PATTERN, "e2e-run-A-signup-1@example.org")
    assert not re.match(seed_persona.THROWAWAY_EMAIL_PATTERN, "e2e-run-A-signup-1@evil.example.org")


def test_the_harness_carries_the_seeded_application_data_the_oracle_renders():
    """A-S5 ruling 2, the same pin one level deeper. Two of the fifteen approved states RENDER
    seeded application data: the applicant-answer card shows `needs-review@`'s `info_request`
    (the reference gets it through A9.1's `startAnswerNote`), and the re-apply form is filled with
    `declined@`'s `fields` on both targets. If the seed and the harness ever disagreed, the two
    targets would render different words and fifteen baselines would be wrong — so they are one
    fact in two languages, like the password and the token pattern above."""
    from scripts import seed_persona

    harness = (ROOT / "frontend" / "tests" / "harness.ts").read_text()
    note = re.search(r"^export const NEEDS_REVIEW_INFO_REQUEST = '([^']+)';$", harness, re.MULTILINE)
    assert note, "frontend/tests/harness.ts no longer defines NEEDS_REVIEW_INFO_REQUEST"
    assert note.group(1) == seed_persona.NEEDS_REVIEW_INFO_REQUEST

    block = re.search(r"^export const DECLINED_FIELDS = \{\n(.*?)^\} as const;$", harness, re.MULTILINE | re.DOTALL)
    assert block, "frontend/tests/harness.ts no longer defines DECLINED_FIELDS as a literal object"
    presented = dict(re.findall(r"^\s*(\w+): '(.*)',?$", block.group(1), re.MULTILINE))
    presented["affirm"] = bool(re.search(r"^\s*affirm: true,?$", block.group(1), re.MULTILINE))
    assert presented == seed_persona.DECLINED_FIELDS, (presented, seed_persona.DECLINED_FIELDS)


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


def test_claude_md_counts_the_seven_prototype_props_and_says_which_are_read():
    """Review round 1, M5. The launch-removal section said "the four prototype props" after A5.7
    added a fifth, and described `prototypeBar` as one of the reference's ways into a state — but
    A6.4b removed the only expression that ever read it, so it is declared for the parity check in
    `app-generated.test.ts` and for nothing else.

    Final-review I2 (S6 round 2): the account screens (Task S4/S5) added two more the same way —
    `startNotice` and `startAnswerNote` — so `frontend/src/app.setup.js` declares SEVEN, not five;
    the count was left at "five" after the enumeration in the same paragraph was widened to name
    both, so a green pin was actively blocking the correction. The name loop below now iterates all
    seven, not five, so a future prototype prop added to the design without a matching name here
    fails this pin rather than passing it silently (I2's own secondary finding)."""
    text = (ROOT / "CLAUDE.md").read_text()
    assert "All seven prototype props stay **declared**" in text
    assert "All five prototype props" not in text
    assert "the four prototype props" not in text
    assert "`prototypeBar` is declared for that parity check alone" in text
    # The seven, by name, in the section that lists them.
    section = text.split("## Launch-removal list")[1]
    for prop in ("prototypeBar", "startScreen", "startViewport", "startGate", "me", "startNotice", "startAnswerNote"):
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
    assert len(found) == 10, f"expected the ten harness personas as one line each, read {sorted(found)}"
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

    # A-S4: `IDENTITY_STATE_PERSONAS` (Task S3's `unverified@` and `verified@`) is read alongside
    # `STATE_PERSONAS` — the harness names `verified@` since Task S4, because it is the account the
    # app reaches `gate-apply` as. Both tuples have the same (email, state, display name) shape and
    # neither carries a role grant, so they merge into one map here.
    #
    # A-S5 (Task S5): `invited@` joins them. It is seeded from its own `INVITED_*` constants rather
    # than a tuple, because it is the one account with no usable password — but it is an applicant
    # like the rest, so the same three facts describe it and it is spelled as a triple here.
    state_personas = (
        *seed_persona.STATE_PERSONAS,
        *seed_persona.IDENTITY_STATE_PERSONAS,
        (seed_persona.INVITED_EMAIL, seed_persona.INVITED_STATE, seed_persona.INVITED_NAME),
    )
    seeded_roles: dict[str, tuple[str, ...]] = {
        seed_persona.PERSONA_EMAIL: seed_persona.PERSONA_ROLES,
        **{email: roles for email, roles in seed_persona.ORACLE_PERSONAS},
        **{email: () for email, _state, _name in state_personas},
    }
    seeded_names: dict[str, str] = {
        seed_persona.PERSONA_EMAIL: seed_persona.PERSONA_NAME,
        **{email: seed_persona.PERSONA_NAME for email, _roles in seed_persona.ORACLE_PERSONAS},
        **{email: name for email, _state, name in state_personas},
    }
    # Only the three members carry an affiliation; an applicant has none to confirm yet, which is
    # rather the point for `declined@`.
    members = {seed_persona.PERSONA_EMAIL, *(email for email, _roles in seed_persona.ORACLE_PERSONAS)}
    seeded_states: dict[str, str] = {email: state for email, state, _name in state_personas}

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


# --- Task I9a: the identity wave's operator documentation -----------------------------------------
# Four tests: two are PINS on what I4-I6 and I8a already made true (the variables, the launch
# removal), two watch documentation this task wrote (the runbook's endpoints, the Resend DNS table).
# `test_operator_token_is_retired` is deliberately NOT here: controller amendment A-I9 (2026-09-07)
# splits I9, and the retirement of `API_SECRET_KEY` / `app/api/auth_stub.py` waits for the
# `PM_API_TOKEN` GitHub secret to exist (Task I9b).


IDENTITY_VARIABLES = ("RESEND_API_KEY", "RESEND_WEBHOOK_SECRET", "EMAIL_ALLOWLIST", "LINK_BASE_URL", "HIBP_ENABLED",
                      "CONSOLIDATOR_KEYWORDS", "MAIL_REPLY_TO", "PERSONA_PASSWORD", "MARKET_DATA_PUBLIC", "DB_POOL_MAX")


def _undocumented(name: str, deploy: str, example: str) -> list[str]:
    """The documents in which `name` is not DOCUMENTED — which is a stronger claim than present.

    `DEPLOY.md` must carry it as a backticked name (`` `VAR` ``, which is how every row of the
    Variables table names its variable) or as a whole table cell (`| VAR |`). `.env.example` must
    carry it as a line that assigns it, set or commented out — `VAR=` or `# VAR=`, the same form
    `test_every_setting_is_documented_in_env_example_and_deploy_md` requires of every `Settings`
    field.

    Both patterns are bounded, and that is the point (I9a fix round 1, Minor 5). This test used to
    ask `var in text`, and the mutation probe meant to prove it bites did not: renaming the
    `.env.example` row to `# PROBE_REMOVED_PERSONA_PASSWORD=` left it GREEN, because the token was
    still a substring of the longer name. A bare substring proves a name appears somewhere in a
    document — in a sentence, inside another identifier, in a code block about something else — not
    that an operator can find the row that tells them what to set."""
    missing = []
    if not re.search(rf"(?:`{re.escape(name)}`|\|\s*{re.escape(name)}\s*\|)", deploy):
        missing.append("DEPLOY.md")
    if not re.search(rf"(?m)^#?\s*{re.escape(name)}=", example):
        missing.append(".env.example")
    return missing


def test_identity_variables_are_documented():
    """Every variable Wave 2a introduced, in BOTH documents, as a row rather than a mention.

    `test_every_setting_is_documented_in_env_example_and_deploy_md` above already covers each field
    of `Settings`, which is most of this list. `PERSONA_PASSWORD` is the one that is NOT a setting —
    nothing in the api or the worker reads it, only `scripts/seed_persona.py` does — so it is the one
    that could have left both documents with nothing to notice."""
    deploy = (ROOT / "DEPLOY.md").read_text()
    example = (ROOT / ".env.example").read_text()
    undocumented = {var: where for var in IDENTITY_VARIABLES if (where := _undocumented(var, deploy, example))}
    assert undocumented == {}, f"identity variables not documented as a row: {undocumented}"


def test_launch_removal_list_is_executed():
    """A PIN, not a change: Task I8a executed CLAUDE.md's launch-removal list through the D15
    amendment engine (A6/A7, ruled D-I8-6), so the list left the DESIGN and the generated files
    lost it with it. This is what stops any of it coming back — a regenerated `App.vue`/`logic.js`
    carrying the jump bar, the access-state shortcuts or the demo credentials fails here."""
    app_vue = (ROOT / "frontend" / "src" / "App.vue").read_text()
    logic = (ROOT / "frontend" / "src" / "logic.js").read_text()
    main = (ROOT / "frontend" / "src" / "main.ts").read_text()
    assert "jumpTo" not in logic, "the prototype jump bar's navigation is back in logic.js"
    assert "gateStates" not in app_vue, "the 'Prototype — access states' shortcuts are back in App.vue"
    assert "r.mendes@example.com" not in logic, "the pre-filled demo credentials are back in logic.js"
    assert "startViewport" not in main, "main.ts passes the startViewport prop again (the app reads ?viewport= only)"


def test_identity_runbook_endpoints_exist():
    """`docs/RUNBOOK-identity.md` is the operator page for Wave 2a, and every call it tells an
    operator to make is written in backticks as `GET /api/…` / `POST /api/…`.

    Walked against `app.main`'s own route table, so a renamed route, a mistyped path or a path
    parameter spelled differently from the router's fails here rather than at 2 a.m. in front of a
    404. Paths are written as TEMPLATES (`{account_id}`, `{token_id}`, `{application_id}` — the
    routers' own parameter names), never with a literal id, and never with a query string inside
    the backticks: the route table holds templates and nothing else.

    The walk is `tests/conftest.py::walk_routes`, shared rather than restated: FastAPI 0.141 keeps
    an included router as a WRAPPER object instead of flattening its routes into `app.routes`, so
    the obvious `{r.path for r in app.routes}` sees `/robots.txt`, `/` and the SPA catch-all and
    nothing else — every `/api/*` path reads as absent, which would have made this test fail
    against a perfectly correct runbook. One walker, in the conftest both consumers can reach
    (I9a review, Minor 4: it used to live in `tests/auth/test_permissions.py`, so reorganising
    `tests/auth/` would have broken this docs test)."""
    from app.main import app
    from tests.conftest import walk_routes

    templates = {path for _method, path, _route in walk_routes(app.routes)}
    runbook = (ROOT / "docs" / "RUNBOOK-identity.md").read_text()
    paths = set(re.findall(r"`(?:GET|POST) (/api/[^`\s]+)`", runbook))
    assert paths, "the runbook names no endpoints at all"
    missing = sorted(p for p in paths if p not in templates)
    assert missing == [], f"docs/RUNBOOK-identity.md names paths app.main does not serve: {missing}"


def test_deploy_md_documents_the_resend_dns_records():
    """Task I9a. Nothing sends from `foundation.vin` until the sender-domain records resolve, and
    the values are John's to copy out of the Resend dashboard — so DEPLOY.md carries the record
    NAMES and an explicit placeholder in every VALUE cell, and never a value. (The same rule the
    `RESEND_API_KEY` row already states, applied to the records beside it.)"""
    text = (ROOT / "DEPLOY.md").read_text()
    assert "## Resend DNS" in text, "the sender-domain records are undocumented"
    for token in ("DKIM", "SPF", "DMARC", "_dmarc"):
        assert token in text, token
    placeholder = "value from the Resend dashboard"
    assert text.count(placeholder) >= 5, f"every VALUE cell must read {placeholder!r} — DKIM x3, SPF, DMARC"
    assert "scripts/bootstrap_admin.py" in text, "the first-admin bootstrap command is undocumented"


def _runbook_decision_table() -> dict[str, dict[str, str]]:
    """`docs/RUNBOOK-identity.md` §3's decision table, keyed by action.

    One row per action, written as `| \\`action\\` | From | To | Note | Email | Effect |` — the same
    "transcribed server table, pinned back against the server" arrangement
    `test_the_admin_users_tables_match_the_api` uses for `frontend/src/admin/users.ts`."""
    text = (ROOT / "docs" / "RUNBOOK-identity.md").read_text()
    rows: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        m = re.match(r"^\| `(\w+)` \| ([^|]*)\| ([^|]*)\| ([^|]*)\| ([^|]*)\| ([^|]*)\|$", line)
        if m:
            action, frm, to, note, email, effect = (g.strip() for g in m.groups())
            rows[action] = {"from": frm, "to": to, "note": note, "email": email, "effect": effect}
    return rows


def test_the_runbook_decision_table_matches_the_api():
    """Review Minor 7. §3 of the runbook transcribes three server tables — `TRANSITIONS`,
    `NOTE_REQUIRED` and `EMAIL` — and until this pin the only thing watching it was the endpoint
    walk, which cannot see a wrong from-state or a missing "a note is required". An operator reading
    a stale row would take a 409 or a 422 at click time and have no way to know the page was wrong.

    Deliberately NOT a check that the table is complete in the other direction on `from`: `revoke`'s
    row says "every state but `revoked`" in prose, so what is pinned for it is that the prose is
    TRUE of the API (every account state except `revoked`), which is the same fact spelled two ways."""
    from app.api.admin_users import ACCOUNT_STATES, EMAIL, NOTE_REQUIRED, TRANSITIONS

    table = _runbook_decision_table()
    assert sorted(table) == sorted(TRANSITIONS), "the runbook's decision table and TRANSITIONS name different actions"
    for action, row in table.items():
        allowed_from, to = TRANSITIONS[action]
        assert row["to"] == f"`{to}`", (action, row["to"])
        if action == "revoke":
            assert row["from"] == "every state but `revoked`", row["from"]
            assert frozenset(ACCOUNT_STATES) - {"revoked"} == allowed_from, "revoke's prose no longer describes TRANSITIONS"
        else:
            assert frozenset(re.findall(r"`(\w+)`", row["from"])) == allowed_from, (action, row["from"])
        required = action in NOTE_REQUIRED
        assert ("**required**" in row["note"]) is required, (action, row["note"], required)
        templates = {template for (_kind, act), template in EMAIL.items() if act == action}
        if templates:
            missing = sorted(t for t in templates if f"`{t}`" not in row["email"])
            assert missing == [], f"{action}: the runbook does not name the email(s) it sends: {missing}"
        else:
            assert "**none**" in row["email"], f"{action} sends no email; the table must say so"


def test_the_identity_spec_states_the_unverified_re_issue_rule():
    """I9a re-review, Important. Task I4's confirmed default — "a duplicate sign-up sends the
    `account_exists` e-mail (equal work on both paths)" — stopped being true of an `unverified`
    address when I9a fix round 1 made that path re-issue the verification link, and the spec is the
    document John's rulings live in: a default recorded there and contradicted by the code is how a
    later task re-implements the thing that was changed on purpose.

    Pinned on the SPEC rather than on the runbook because the runbook describes an operator's day
    and the spec records the decision. Both halves are asserted, so neither can drift back alone."""
    spec = (ROOT / "docs" / "superpowers" / "specs" / "2026-09-05-identity-access-email-design.md").read_text()
    default = next((line for line in spec.splitlines() if "Task I4: a duplicate sign-up" in line), None)
    assert default is not None, "the spec no longer records Task I4's duplicate-sign-up default"
    assert "re-issues a fresh 24 h verification link" in default, (
        "the spec's I4 default does not state the unverified re-issue rule (app/api/auth.py::signup)"
    )
    assert "`unverified`" in default and "`account_exists`" in default, (
        "the amended default must still name both halves: `account_exists` from verified onward, re-issue while unverified"
    )
    assert "amended 2026-09-07" in default, "the amendment is undated"


def test_deploy_md_documents_how_to_seed_qa():
    """The seed run is a hand operation on QA; DEPLOY.md is where hand operations live."""
    deploy = (ROOT / "DEPLOY.md").read_text()
    assert "## Seeding the demo hospitals (QA)" in deploy
    assert "python scripts/seed_listings.py --reset" in deploy
    assert "never on production without John's go" in deploy
    # L4 review round 1: the two operator-facing outcomes the runbook must not leave out — the
    # flag that buys a production run, and the exit code that says a seller owns a seed slug.
    assert "scripts/seed_listings.py --production" in deploy
    # M8: the phrase, not a bare backtick-5 that any digit in a 190-line runbook would satisfy.
    assert "`5` — a **non-seed listing** already owns one of the seed slugs" in deploy
    # I1: an undeclared ENVIRONMENT is a refusal, and the runbook says which code it is.
    assert "`ENVIRONMENT` unset" in deploy
    # M4: the realistic exit-4 that is not the file's fault.
    assert "unmigrated database" in deploy
    # M11: listed_at moves on every import — the one claim a reader reasoning about the listing
    # page's ordering would rely on.
    assert "recomputed from `listed_days_ago`" in deploy
    # M3: the headline command is the plain import; `--reset` (fresh ids, and it buys nothing the
    # plain import does not since A-L4) is demoted beneath it.
    section = deploy.split("## Seeding the demo hospitals (QA)", 1)[1].split("\n## ", 1)[0]
    plain = section.find("python scripts/seed_listings.py  ")
    reset = section.find("python scripts/seed_listings.py --reset")
    assert 0 <= plain < reset, "the runbook's headline command must be the plain import (M3)"
    # L5 review round 2, M8: the seeder does not invalidate the 60 s Redis cache in front of
    # `GET /api/listings` (ruled, A-L5.1(4)), so the runbook has to say that a browse still showing
    # the previous eighteen straight after a seed is that cache and not a failed import —
    # otherwise the next operator re-runs a successful seed looking for a fault.
    assert "caches each page in Redis for 60 s" in section
    assert "the seeder does not invalidate it" in section
    assert "not a failed import" in section


# --- Task S6: docs and drift, once the account screens (S1-S5), the reseed (S7) and main (M1) are
# in ------------------------------------------------------------------------------------------
# Every count below is a fact stated by hand in prose somewhere (CLAUDE.md, LOCAL_AMENDMENTS.md,
# the runbook) that a generated or hand-maintained SOURCE also carries — the same drift class as
# the backend-gate and coverage-exclusion pins above, applied to the numbers this merge changed.


def test_claude_md_approved_screen_count_matches_screens_ts():
    """`frontend/tests/screens.ts`'s `SCREENS` grew from 28 (Browse V3) to 43 once Wave 2a's
    fifteen account-screen states (spec §6, controller amendment A-S5) were appended, and
    CLAUDE.md's "Layout" line names the count by hand. Counted the same way
    `frontend/tests/cross-plan-deltas.test.ts` counts it on the TypeScript side (`SCREENS.length`);
    here it is a regex over the array literal, since nothing in this suite runs a TS parser."""
    screens_ts = (ROOT / "frontend" / "tests" / "screens.ts").read_text()
    # Anchored to the START of a line: several steps also call `getByRole(..., { name: '...' })`,
    # which is the SAME four characters but not a new `Screen` entry — the naive substring count
    # read 48 here, not 43, until this anchored it (measured while writing this pin).
    count = len(re.findall(r"^\s*\{ name: '", screens_ts, re.MULTILINE))
    assert count > 28, "frontend/tests/screens.ts lost states, or the `{ name: '...` marker changed"

    claude = (ROOT / "CLAUDE.md").read_text()
    layout = next((line for line in claude.splitlines() if line.startswith("`frontend/` Vue app")), None)
    assert layout is not None, "CLAUDE.md's Layout line is missing or no longer starts with `frontend/` Vue app"
    assert f"the {count} approved states" in layout, (
        f"CLAUDE.md's Layout line does not name {count}, frontend/tests/screens.ts's real SCREENS.length: {layout!r}"
    )


def test_runbook_names_the_five_account_routes():
    """Task S6. Five routed pages joined the app with the account screens
    (`frontend/src/router/routes.ts`): `/signup`, `/forgot` (no token) and `/verify`, `/reset`,
    `/accept-invite` (each reads a `?token=` once). An operator reading a bug report about one of
    them needs the runbook to name it — the same "a path here is a path the server serves" contract
    `test_identity_runbook_endpoints_exist` holds the API paths to, extended to the frontend
    routes the verify/reset/invite links and a bare sign-up/forgot visit actually open."""
    text = (ROOT / "docs" / "RUNBOOK-identity.md").read_text()
    missing = [r for r in ("/signup", "/forgot", "/verify", "/reset", "/accept-invite") if f"`{r}`" not in text]
    assert missing == [], f"docs/RUNBOOK-identity.md does not name these account routes: {missing}"


def test_claude_md_amendment_family_and_entry_counts_match_design_amendments():
    """The merge of this branch's account-screen amendments (A8, A9) with `main`'s A10/A11 grew
    both the family count and the entry count `CLAUDE.md`'s "Source of truth" paragraph states by
    hand — it read "Nine families, 54 entries … 30 literals" before this task and named A10/A11
    but not A8/A9, the same drift class the pre-merge count went stale by.

    Families: a literal amendment's id (`A2`, `A2.2`, `A5.3a`, `A10.2`, …) always starts `A` then a
    number, so its family is that number; A1 itself never appears as a literal id — it is DERIVED
    (`deriveTypographyB`, driven by V2 vs the pristine bundle) — so it is added by hand as the one
    family the regex cannot see. Entries: the literal count plus A1's own derived count, read from
    `design-amendments.test.ts`'s own `Array.from({ length: N }, ...)` rather than duplicated here,
    so the two files cannot drift against each other silently."""
    ts = (ROOT / "frontend" / "tests" / "design-amendments.ts").read_text()
    literal_families = re.findall(r"id: 'A(\d+)", ts)
    assert literal_families, "frontend/tests/design-amendments.ts: no literal amendment ids found (id: 'A<n>...)"
    family_count = len({int(n) for n in literal_families}) + 1  # +1 for A1, derived not literal
    literal_count = len(literal_families)

    test_ts = (ROOT / "frontend" / "tests" / "design-amendments.test.ts").read_text()
    a1_match = re.search(r"Array\.from\(\{ length: (\d+) \}, \(_, i\) => `A1\.\$\{i \+ 1\}`\)", test_ts)
    assert a1_match, "design-amendments.test.ts no longer derives A1's ids from Array.from({ length: N }, ...)"
    a1_count = int(a1_match.group(1))
    entry_count = literal_count + a1_count

    number_words = {n: w for n, w in enumerate(
        ("Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten",
         "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen"))}
    assert family_count in number_words, f"no spelled-out word on hand for {family_count} families"

    claude = (ROOT / "CLAUDE.md").read_text()
    assert f"{number_words[family_count]} families, {entry_count} entries" in claude, (
        f"CLAUDE.md's family/entry count sentence does not match design-amendments.ts: "
        f"{family_count} families, {entry_count} entries ({a1_count} derived + {literal_count} literals)"
    )
    assert f"A1's {a1_count} derived edits plus {literal_count} literals" in claude


def test_local_amendments_row_count_matches_design_amendments():
    """`LOCAL_AMENDMENTS.md` carries one table row per amendment id, with A1's derived edits
    collapsed to a single row (`frontend/tests/design-amendments.test.ts` proves the collapse and
    the ordering on the TypeScript side); here the row count is cross-checked against the same
    literal-id count the family/entry test above reads, so a row silently added or dropped on
    either side fails here rather than only in the frontend suite."""
    ts = (ROOT / "frontend" / "tests" / "design-amendments.ts").read_text()
    literal_count = len(re.findall(r"id: 'A(\d+)", ts))
    md = (ROOT / "docs" / "design-reference" / "design_handoff_practice_match_v3" / "LOCAL_AMENDMENTS.md").read_text()
    rows = re.findall(r"^\|\s*(A[\w.]+)\s*\|", md, re.MULTILINE)
    assert len(rows) == literal_count + 1, (
        f"LOCAL_AMENDMENTS.md has {len(rows)} rows; expected {literal_count + 1} "
        f"({literal_count} literal amendments + one collapsed A1 row)"
    )


def test_runbook_qa_parity_sign_in_budget_matches_the_harness_trace():
    """S6 review round 1 (Critical). The runbook's QA parity run section stated the sign-in budget
    as "sixteen" of `SIGNIN_IP`'s thirty — a stale figure carried over from the account-screens
    plan's A-S5 (3) paragraph, which A-S5.1 already corrected to FOURTEEN (traced exactly against
    real `POST /api/auth/signin` calls, not estimated: `frontend/tests/harness.ts`'s "THE BUDGET"
    docstring, 7 + 2 + 3 + 1 + 1). The reseed itself spends no sign-ins, so the number the runbook
    quotes for "one full parity run" is the harness's traced number and nothing else.

    Pinned by reading the word out of BOTH files rather than hard-coding it here, so the two can
    never drift apart silently again — whichever one next changes, this fails until the other
    agrees with it."""
    harness = (ROOT / "frontend" / "tests" / "harness.ts").read_text()
    budget_line = next((line for line in harness.splitlines() if "THE BUDGET" in line), None)
    assert budget_line is not None, "frontend/tests/harness.ts no longer carries a 'THE BUDGET' line"
    harness_match = re.search(r"THE BUDGET — (\w+) of thirty", budget_line)
    assert harness_match, f"could not read the traced sign-in count out of: {budget_line!r}"

    runbook = (ROOT / "docs" / "RUNBOOK-identity.md").read_text()
    runbook_match = re.search(r"(\w+) of `SIGNIN_IP`'s thirty sign-ins per FIXED", runbook)
    assert runbook_match, "docs/RUNBOOK-identity.md no longer states the QA parity sign-in budget this way"

    assert runbook_match.group(1).lower() == harness_match.group(1).lower(), (
        f"docs/RUNBOOK-identity.md says {runbook_match.group(1)!r} of thirty sign-ins; "
        f"frontend/tests/harness.ts's traced budget says {harness_match.group(1)!r} — they must agree"
    )


# --- S6 fix round 2: every stale statement the final review and its docs-drift sweep found ---------


def _collapse_whitespace(text: str) -> str:
    """Markdown soft-wraps one prose sentence differently in different documents (a table row on
    one line in `DEPLOY.md`, wrapped across several in `docs/RUNBOOK-identity.md`), so a literal
    substring search across documents has to look past line breaks to compare the same words."""
    return re.sub(r"\s+", " ", text)


PERSONA_PASSWORD_KEYCHAIN_NOTE = (
    "held in the operator's macOS Keychain (service `practice-match-qa`, account "
    "`PERSONA_PASSWORD`; read with `security find-generic-password -a PERSONA_PASSWORD -s "
    "practice-match-qa -w` into a subprocess environment, never printed); read by no service; "
    "passed to the seed and the harness through the shell; never on production"
)

PERSONA_PASSWORD_OLD_RAILWAY_PHRASE = "stored on the QA `api` service in Railway as the operator's secret store"


def test_persona_password_keychain_storage_is_one_fact_in_every_document():
    """Controller amendment A-S6.2 (2026-09-08; John's ruling on default #5) supersedes A-S6.1's
    storage sentence: `PERSONA_PASSWORD` was removed from the QA `api` service on 2026-09-08 (no
    service ever read it) and now lives only in the operator's macOS Keychain (service
    `practice-match-qa`, account `PERSONA_PASSWORD`). `DEPLOY.md`, `.env.example` and both halves of
    `docs/RUNBOOK-identity.md`'s test/QA-account documentation (§11 and §12) all quoted A-S6.1's
    Railway sentence verbatim; each now has to state the SAME new fact, in these words, and none of
    them may still claim the password sits in Railway (A-S6.1's own paragraph is the one place that
    keeps the old wording, as history, so this test does not scan it). Whitespace is collapsed
    before comparing (see `_collapse_whitespace`), because the same sentence wraps differently in
    each document."""
    deploy = _collapse_whitespace((ROOT / "DEPLOY.md").read_text())
    example = _collapse_whitespace((ROOT / ".env.example").read_text())
    runbook = (ROOT / "docs" / "RUNBOOK-identity.md").read_text()
    section_11 = _collapse_whitespace(runbook.split("## 11. Test and QA accounts")[1].split("## 12.")[0])
    section_12 = _collapse_whitespace(runbook.split("## 12. QA parity run")[1])

    for name, text in (
        ("DEPLOY.md", deploy),
        (".env.example", example),
        ("docs/RUNBOOK-identity.md §11", section_11),
        ("docs/RUNBOOK-identity.md §12", section_12),
    ):
        assert PERSONA_PASSWORD_KEYCHAIN_NOTE in text, f"{name} does not carry A-S6.2's Keychain sentence verbatim"
        assert PERSONA_PASSWORD_OLD_RAILWAY_PHRASE not in text, (
            f"{name} still claims PERSONA_PASSWORD is stored on the QA `api` service in Railway "
            "(A-S6.1, superseded by A-S6.2)"
        )


def test_runbook_qa_parity_command_pins_the_playwright_config_flag():
    """Final-review docs-drift sweep, item 3. `frontend/tests/playwright.config.ts` is the only
    Playwright config in the repo, and `frontend/package.json`'s `test:e2e` script already runs
    `playwright test --config=tests/playwright.config.ts --project=app` from `frontend/`. The QA
    parity command in the runbook has to match that shape — a bare `npx playwright test
    --project=app` run from the repo root (no `cd frontend`, no `--config=`) cannot find the config
    at all."""
    scripts = json.loads((ROOT / "frontend" / "package.json").read_text())["scripts"]
    assert "--config=tests/playwright.config.ts --project=app" in scripts["test:e2e"], scripts["test:e2e"]
    config_files = list((ROOT / "frontend").rglob("playwright.config.ts"))
    assert [p.relative_to(ROOT / "frontend") for p in config_files] == [Path("tests/playwright.config.ts")], (
        f"expected exactly one config at frontend/tests/playwright.config.ts, found {config_files}"
    )

    runbook = (ROOT / "docs" / "RUNBOOK-identity.md").read_text()
    section_12 = runbook.split("## 12. QA parity run")[1]
    assert "--config=tests/playwright.config.ts --project=app" in section_12, (
        "docs/RUNBOOK-identity.md §12's QA parity command does not pass --config=tests/playwright.config.ts"
    )
    assert "cd frontend" in section_12, "docs/RUNBOOK-identity.md §12's command no longer cds into frontend/ first"


def test_deploy_md_says_ten_test_accounts():
    """Final-review docs-drift sweep, item 11. `DEPLOY.md`'s QA persona accounts bullet said "the
    six `.test` accounts" — stale since Task S3/S7 grew the seed to ten (three members, three
    applicants, four identity-screen accounts)."""
    text = (ROOT / "DEPLOY.md").read_text()
    assert "seeds the ten `.test` accounts" in text, "DEPLOY.md does not say the seed produces ten accounts"
    assert "the six `.test` accounts" not in text


def test_spec_names_verify_me_as_the_verify_token_owner():
    """Final-review docs-drift sweep, item 8. A-S5.2 (S-1) moved the `verify` fixture tokens off
    `unverified@` and onto a tenth account, `verify-me@`, created solely to own them — consuming one
    during a test must never confirm the account the check-email/resend states need to stay
    `unverified`. The design spec's own fixture paragraph still named `unverified@` as the token
    owner; this pins it against `scripts/seed_persona.py`'s own mapping, which is the fact of
    record (`tests/test_docs.py::test_the_harness_fixture_tokens_match_the_seed_scripts_pattern_and_the_three_new_state_emails`
    pins the same mapping on the harness side)."""
    from scripts import seed_persona

    verify_email, _pattern = seed_persona.FIXTURE_TOKENS["verify"]
    assert verify_email == "verify-me@practice-match.test"

    spec = (ROOT / "docs" / "superpowers" / "specs" / "2026-09-07-account-screens-design.md").read_text()
    assert "twelve each of `verify` (for `verify-me@`" in spec, (
        "the spec's fixtures paragraph no longer names verify-me@ as the verify token owner"
    )
    assert "twelve each of `verify` (for `unverified@`" not in spec


def test_runbook_uses_the_singular_railway_variable_list_spelling():
    """Final-review M7 / docs-drift sweep item 7. `CLAUDE.md`'s "Common operations" pins `railway
    variable list --service api --environment QA --json` (the singular, subcommand form the
    installed CLI, 5.26.0, documents); the runbook's QA parity command used the plural
    `railway variables --service api --environment QA --json` instead, which M7 could not rule out
    as simply wrong for the installed CLI. Pinned so the two spellings of the SAME listing
    invocation cannot drift apart again — this checks the exact command CLAUDE.md pins, not merely
    that the word "variable" appears somewhere."""
    claude = (ROOT / "CLAUDE.md").read_text()
    command_match = re.search(r"railway variable list --service api --environment QA --json", claude)
    assert command_match, "CLAUDE.md no longer pins the railway variable list command this test compares against"

    runbook = (ROOT / "docs" / "RUNBOOK-identity.md").read_text()
    assert command_match.group(0) in runbook, (
        "docs/RUNBOOK-identity.md's QA parity command does not use CLAUDE.md's pinned "
        "'railway variable list' spelling"
    )
    assert "railway variables --service api --environment QA --json" not in runbook


# --- Task L7: the seed-listings docs sweep (A-L7 item 6) -------------------------------------------


def test_claude_md_launch_removal_records_the_listings_boot_swap():
    """A-L7 docs sweep item 6. The launch-removal section's fixture-data sentence said the
    fixtures stay "until the listings API replaces it (Seed Listings plan, D6)" while D6 was still
    future work; Task L6 landed the swap (`frontend/src/main.ts` reads the eighteen seeded
    listings through `frontend/src/listings/load.ts` before first paint and installs them into the
    prototype's own `P`/`MARKETS` arrays), so the sentence has to say what actually happens now —
    the API replaces `P` and `MARKETS` at boot, and the fixture arrays stay in `logic.js` only as
    the D6 stub's source for the pixel/DOM gates."""
    claude = (ROOT / "CLAUDE.md").read_text()
    section = claude.split("## Launch-removal list")[1]
    assert "until the listings API replaces it (Seed Listings plan, D6)" not in section, (
        "CLAUDE.md still states the pre-L6 future tense for the listings API swap"
    )
    assert "the API replaces `P` and `MARKETS` at boot" in section
    assert "`frontend/src/main.ts`" in section and "`frontend/src/listings/load.ts`" in section
    assert "the D6 stub's source for the gates" in section
    # ...and the files really do that, so the sentence is not merely plausible prose.
    main_ts = (ROOT / "frontend" / "src" / "main.ts").read_text()
    assert "loadListings" in main_ts and "./listings/load" in main_ts


def test_claude_md_layout_line_names_the_seed_assets_and_scripts():
    """A-L7 docs sweep item 6. The Seed Listings sub-project added `seeds/` (the demo hospital
    data and photographs) and two scripts the Layout line never mentioned, and `scripts/start.sh`
    grew a fourth role (`seed`, Task L4) the line still called three roles."""
    claude = (ROOT / "CLAUDE.md").read_text()
    layout = next((line for line in claude.splitlines() if line.startswith("`frontend/` Vue app")), None)
    assert layout is not None, "CLAUDE.md's Layout line is missing or no longer starts with `frontend/` Vue app"
    assert "`seeds/`" in layout, "CLAUDE.md's Layout line does not name seeds/"
    assert "`seed_listings.py`" in layout
    assert "`prepare_photos.py`" in layout
    assert "roles api|worker|migrate|seed" in layout, (
        "CLAUDE.md's Layout line still calls start.sh's roles api|worker|migrate"
    )
    # ...and that really is what start.sh accepts, not merely what the doc claims.
    start_sh = (ROOT / "scripts" / "start.sh").read_text()
    assert "expected api | worker | migrate | seed" in start_sh


def test_claude_md_common_operations_includes_the_seed_command():
    """A-L7 docs sweep item 6. CLAUDE.md's "Common operations" is the block an operator copies for
    a day's work, and it never named the seeder Task L4 added. It gains the one seed command
    DEPLOY.md documents as the headline (the plain import, not `--reset` — DEPLOY.md's M3
    ruling), with a pointer to the DEPLOY.md section that has the rest."""
    claude = (ROOT / "CLAUDE.md").read_text()
    ops = claude.split("## Common operations")[1]
    assert re.search(r"^python scripts/seed_listings\.py\b", ops, re.MULTILINE), (
        "CLAUDE.md's Common operations block does not carry the plain `python scripts/seed_listings.py` line"
    )
    assert "seed_listings.py --reset" not in ops, (
        "CLAUDE.md's Common operations should name the plain headline import, not --reset (DEPLOY.md's M3 ruling)"
    )
    deploy = (ROOT / "DEPLOY.md").read_text()
    assert "## Seeding the demo hospitals (QA)" in deploy
    assert "Seeding the demo hospitals (QA)" in ops, "CLAUDE.md's seed line should point at DEPLOY.md's section"


def test_deploy_md_exit_codes_match_seed_listings_returns():
    """A-L7 docs sweep item 6. DEPLOY.md's exit-code list is prose, hand-transcribed from
    `scripts/seed_listings.py`'s actual `return` statements; if a future edit added or removed a
    code there without updating the runbook, an operator would diagnose a container by the wrong
    document. Extracted from the script rather than hard-coded, so the two cannot drift apart
    silently."""
    seed = (ROOT / "scripts" / "seed_listings.py").read_text()
    codes = sorted({int(n) for n in re.findall(r"^\s*return (\d+)\b", seed, re.MULTILINE)})
    assert codes == [0, 2, 3, 4, 5], f"scripts/seed_listings.py's return codes moved: {codes}"
    deploy = (ROOT / "DEPLOY.md").read_text()
    section = deploy.split("## Seeding the demo hospitals (QA)", 1)[1].split("\n## ", 1)[0]
    for code in codes:
        assert f"`{code}`" in section, f"DEPLOY.md's seeding section does not document exit code {code}"


# --- Task S8: A-S6.2 — PERSONA_PASSWORD leaves Railway for the operator's Keychain; QA DB_POOL_MAX --


def test_deploy_md_records_qa_db_pool_max_values_and_sizing_rule():
    """A-S6.2 (2026-09-08) has the controller's `DB_POOL_MAX` change on QA — `api` set to `10`,
    `worker` to `4` — recorded in `DEPLOY.md`'s variables table, along with the sizing rule: uvicorn
    serves the api as a single process and celery runs `--concurrency=2` (`scripts/start.sh`) plus
    beat, so the two reuse pools together hold at most 14 idle connections against PostGIS's
    `max_connections` of 100. Checked against the actual code, not just asserted as prose, so the
    two cannot drift apart silently."""
    deploy = (ROOT / "DEPLOY.md").read_text()
    row = next(line for line in deploy.splitlines() if line.startswith("| `DB_POOL_MAX`"))
    assert "`10`" in row, f"DEPLOY.md's DB_POOL_MAX row does not name QA api's value of 10: {row!r}"
    assert "`4`" in row, f"DEPLOY.md's DB_POOL_MAX row does not name QA worker's value of 4: {row!r}"
    assert "api" in row and "worker" in row, "DEPLOY.md's DB_POOL_MAX row does not name which service gets which value"
    assert "14" in row, "DEPLOY.md's DB_POOL_MAX row does not state the combined idle-connection ceiling (14)"
    assert "100" in row, "DEPLOY.md's DB_POOL_MAX row does not name PostGIS's max_connections (100)"

    # ...and that really is what the code does: a single uvicorn process, celery at concurrency 2.
    start_sh = (ROOT / "scripts" / "start.sh").read_text()
    assert '--concurrency="${CELERY_CONCURRENCY:-2}"' in start_sh, (
        "scripts/start.sh's celery concurrency default moved off 2 — DEPLOY.md's 14-connection sizing rule assumes it"
    )
    assert "--workers" not in start_sh, "scripts/start.sh now runs uvicorn with multiple workers — the sizing rule assumes a single process"


def test_a_s6_1_is_marked_superseded_by_a_s6_2_without_being_deleted():
    """Task S8 (docs-vs-code sweep). A-S6.1's storage ruling is now wrong — the password left
    Railway — but it stays in the plan as history (it records a real decision that held for a real
    period), with one added clause pointing at what replaced it. This pins that the clause was
    added and that the original ruling sentence is still there, verbatim, rather than rewritten or
    deleted."""
    plan = (ROOT / "docs" / "superpowers" / "plans" / "2026-09-08-account-screens.md").read_text()
    a_s6_1 = next(line for line in plan.splitlines() if line.startswith("**A-S6.1"))
    assert "superseded by A-S6.2" in a_s6_1, "A-S6.1's paragraph does not carry the added 'superseded by A-S6.2' clause"
    assert (
        "`PERSONA_PASSWORD` IS stored as a Railway variable on the QA `api` service — as the "
        "operator's secret store only"
    ) in a_s6_1, "A-S6.1's original ruling sentence was rewritten or removed rather than kept as history"


PLAN_FILES_WITH_PERSONA_PASSWORD_HISTORY = (
    "docs/superpowers/plans/2026-09-05-practice-match-identity-access-email.md",
    "docs/superpowers/plans/2026-09-08-account-screens.md",
)


def test_persona_password_railway_set_instructions_are_marked_superseded():
    """S8 Round 2 (review Medium finding 1). `docs/superpowers/plans/2026-09-05-practice-match-
    identity-access-email.md`'s Step 1 (the original `railway variables --set PERSONA_PASSWORD=…`
    instruction) and its R8 risk-register row (`rotate with railway variables --set`) are live,
    unmarked instructions that would recreate exactly the Railway storage A-S6.2 ruled against —
    Task S8's file list didn't cover this plan, but a stale, actionable instruction left in ANY
    plan is the same defect the Keychain sweep exists to catch. Rather than special-case those two
    lines, this pins the general rule for both identity-era plans: any line that mentions
    `PERSONA_PASSWORD` and `railway variables --set` in the same breath must also say "superseded"
    on that same line, so a future edit that adds another such instruction fails here too."""
    for relpath in PLAN_FILES_WITH_PERSONA_PASSWORD_HISTORY:
        text = (ROOT / relpath).read_text()
        for line in text.splitlines():
            if "PERSONA_PASSWORD" in line and "railway variables --set" in line:
                assert "superseded" in line, (
                    f"{relpath}: line mentions PERSONA_PASSWORD and `railway variables --set` "
                    f"but is not marked superseded: {line!r}"
                )


# --- A-L10: the seed photographs match the design's captions ---------------------------------


def test_the_seed_plan_records_a_l10_and_deploy_md_names_the_curation_file():
    """A-L10 (John, 2026-09-09: "explain where the image description is coming from…" and "match
    the description"). Two documents of record have to carry this or the next operator repeats
    A-L9's mistake: the plan says WHY the captions are the design's and why a filename is not
    evidence, and DEPLOY.md — where hand operations live — says which file decides and what an
    empty slot means. Pinned to the claims, not to prose, so a rewrite that keeps the meaning
    still passes and a deletion does not."""
    plan = (ROOT / "docs" / "superpowers" / "plans" / "2026-09-06-practice-match-seed-listings.md").read_text()
    record = plan.split("**Controller amendment A-L10")[-1]
    assert len(plan.split("**Controller amendment A-L10")) == 2, "the A-L10 record is missing or duplicated"
    assert '"match the description"' in record, "the record does not quote John's ruling"
    assert "photoSet(p)" in record and "the DESIGN's own" in record, (
        "the record must say where the caption comes from — the design's fixed slot captions"
    )
    assert "curation.json" in record
    assert "73" in record and "108" in record and "35" in record, "the record does not state 73 of 108 filled"
    for slug in ("1111_pet_hospital", "ghi_veterinary_hospital", "pqr_veterinary_hospital",
                 "stu_veterinary_specialist_center"):
        assert slug in record, f"the record does not name {slug} as needing clean images from John"
    assert "Supersedes A-L9's fallback rule" in record
    assert "placeholder" in record, "the record does not say an empty slot renders the design's placeholder"

    deploy = (ROOT / "DEPLOY.md").read_text()
    section = deploy.split("## Seeding the demo hospitals (QA)", 1)[1].split("\n## ", 1)[0]
    assert "A-L10" in section
    assert "`seeds/hospitals/photos/curation.json` is the source of truth" in section
    assert "stays\nempty" in section or "stays empty" in section
    assert "placeholder" in section, "the runbook does not say an empty slot shows the design's placeholder"
    # …and the file it points at really is there and really covers the seeds.
    curation = json.loads((ROOT / "seeds" / "hospitals" / "photos" / "curation.json").read_text())
    named = {slug for slug in curation if not slug.startswith("_")}
    seeds = {h["slug"] for h in json.loads((ROOT / "seeds" / "hospitals.json").read_text())["hospitals"]}
    assert named == seeds, "curation.json and seeds/hospitals.json name different hospitals"
    assert "_comment" in curation, "curation.json lost the comment that says what it is"


# --- A-L11: every uploaded photograph renders, with its own description -----------------------


def test_the_seed_plan_records_a_l11_and_deploy_md_says_every_image_renders():
    """A-L11 (John, 2026-09-09: "HAS FAILED and wiped out all the images … render ALL images").
    The same two documents of record as A-L10, for the hotfix that reverses its rule: the plan
    says what went wrong, what the rule is now and what carries the words; DEPLOY.md — where hand
    operations live — says what an operator will actually see on the detail page. Pinned to the
    claims, not to prose, so a rewrite that keeps the meaning still passes and a deletion does
    not."""
    plan = (ROOT / "docs" / "superpowers" / "plans" / "2026-09-06-practice-match-seed-listings.md").read_text()
    assert len(plan.split("**Controller amendment A-L11")) == 2, "the A-L11 record is missing or duplicated"
    record = plan.split("**Controller amendment A-L11")[-1]
    assert "render ALL images" in record, "the record does not quote John's ruling"
    # The root cause, in the terms that make it a design fact and not a bug report.
    assert "photoSet(p)" in record
    # A-L11 review (m4): the TRUE counts. The brief's "117 of 190 dropped" was arithmetic
    # (73 kept + 117 = 190) and the folders actually hold 195 — A-L10 rendered 73 of them and
    # A-L11 renders all 195. A record that states a count nobody can reproduce is worse than one
    # that states none, so the superseded numbers may not come back.
    assert "195" in record and "73" in record, "the record does not state what was rendered"
    for superseded in ("117", "190"):
        assert superseded not in record, f"the A-L10 arithmetic {superseded} is back in the record"
    # What now carries the description, and what renders it.
    assert "A15" in record and "photo_captions" in record
    # A-L11 review (M1): 024 sat inside the Census plan's reserved 017-059 (that plan's D14).
    # Platform and hotfix migrations on `main` take 090-099, and the record is where the next
    # implementer reads that.
    assert "090_listing_photo_captions.sql" in record
    assert "090" in record and "099" in record, "the record does not state the reserved range"
    assert "Supersedes A-L10" in record, "the record does not retire A-L10's empty-slot rule"
    # The one thing this hotfix deliberately did NOT change, so the next reader does not "fix" it.
    assert "Six views per practice" in record, "the queued design-copy question is not recorded"

    deploy = (ROOT / "DEPLOY.md").read_text()
    section = deploy.split("## Seeding the demo hospitals (QA)", 1)[1].split("\n## ", 1)[0]
    assert "A-L11" in section
    assert "is rendered" in section and "195 of them today" in section, (
        "the runbook does not say that every image John supplies is rendered, and how many that is"
    )
    # Hyphen-minus, deliberately: the runbook writes the range that way and RUF001 refuses an
    # en dash in a source literal.
    assert "positions 1-6" in section, "the runbook does not say which positions the design's slots are"
    assert "supplier" in section, "the runbook does not say where a photograph's description comes from"

    # M1 again: the range belongs where an operator adding a migration will look for it, which is
    # DEPLOY.md's own Migrations section and not the seeding runbook.
    migrations = deploy.split("## Migrations", 1)[1].split("\n## ", 1)[0]
    assert "090" in migrations and "099" in migrations, (
        "DEPLOY.md's Migrations section does not record the platform/hotfix range"
    )
    assert "017" in migrations and "059" in migrations, (
        "DEPLOY.md's Migrations section does not say which range is the Census plan's"
    )
