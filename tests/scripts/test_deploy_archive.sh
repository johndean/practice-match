#!/usr/bin/env bash
# deploy.sh must upload the COMMITTED TREE of an explicit SOURCE_DIR — never the working
# directory, and never a tree the Railway CLI resolved for itself.
#
# P14's root cause, measured 2026-09-07: run from the linked worktree
# `.worktrees/feat-browse-v3` (HEAD 17f40c3), `railway up` (CLI 5.26.0) followed that
# worktree's `.git` *pointer file* back to the main repository directory and uploaded
# MAIN's tree, while `/api/healthz` reported the branch's sha — the `COMMIT_SHA` service
# variable deploy.sh had just set. QA served main's code under the branch's name and
# verify-deploy.sh could not tell. Every case below exists to keep one half of that
# defect closed: the upload is `git archive HEAD` of SOURCE_DIR, and SOURCE_DIR is ours
# to name.
#
# Same hermetic fake-`railway` harness as test_deploy_guard.sh and test_verify_deploy.sh:
# a fake CLI shadows the real one on PATH and records every invocation. This one also
# records a manifest of the directory `railway up` was handed, and models Railway's
# deployment list well enough to exercise the log-stream-timeout fallback: a deployment
# comes into existence only when `up` creates one, and its status is popped per poll.
# Scratch git repositories — including a real `git worktree add`, so the `.git` pointer
# file is the genuine article — stand in for the checkouts. Nothing here touches the
# network or a Railway account.
set -euo pipefail; cd "$(dirname "$0")/../.."
fail() { echo "FAIL: $*"; exit 1; }
[[ -x scripts/deploy.sh ]] || fail "scripts/deploy.sh missing or not executable"

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
export FAKE_LOG="$tmp/log"; : > "$FAKE_LOG"
export FAKE_STATE="$tmp/state"
reset_state() { rm -rf "$FAKE_STATE"; mkdir -p "$FAKE_STATE"; }
reset_state

cat > "$tmp/railway" <<'F'
#!/usr/bin/env bash
echo "railway $*" >> "$FAKE_LOG"
# --service <name>, wherever it sits in the argument list.
svc=""; prev=""
for a in "$@"; do [[ "$prev" == "--service" ]] && svc="$a"; prev="$a"; done
OLD_ROW='{"id":"dep-old","status":"SUCCESS","createdAt":"2026-09-07T09:00:00Z"}'
case "$1" in
  status) printf '{"name":"%s"}\n' "${FAKE_PROJECT:-Practice Match}" ;;
  variable) : ;;
  up)
    echo "UP $*" >> "$FAKE_LOG"
    path="$2"
    if [[ -d "$path" ]]; then
      echo "UPLOAD_ROOT $path" >> "$FAKE_LOG"
      (cd "$path" && find . -maxdepth 2 -print | sed 's|^|UPLOAD_ENTRY |') >> "$FAKE_LOG"
      [[ -f "$path/pyproject.toml" ]] && sed 's|^|UPLOAD_PYPROJECT |' "$path/pyproject.toml" >> "$FAKE_LOG"
      [[ -f "$path/BUILD_SHA" ]] && sed 's|^|UPLOAD_BUILD_SHA |' "$path/BUILD_SHA" >> "$FAKE_LOG"
    fi
    # A real upload creates a deployment. FAKE_UP_NO_DEPLOYMENT is the C2 hole: `up` failed
    # at UPLOAD time, so nothing was created and the previous (SUCCESS) deployment is still
    # the newest one Railway will report.
    if [[ -z "${FAKE_UP_NO_DEPLOYMENT:-}" ]]; then
      # Unquoted on purpose: "BUILDING SUCCESS" becomes one status per line, popped per poll.
      printf '%s\n' ${FAKE_DEPLOY_STATUSES:-SUCCESS} > "$FAKE_STATE/dep-$svc"
    fi
    # The measured failure mode: the upload succeeds, then the CLI's own log stream times
    # out and `up` exits non-zero while the deployment carries on to SUCCESS.
    [[ -n "${FAKE_UP_FAILS:-}" ]] && { echo "reqwest error: error sending request: operation timed out" >&2; exit 1; }
    exit 0
    ;;
  deployment)
    # `deployment list --json`. FAKE_DEPLOYMENT_FAILS makes the subcommand fail the way a
    # transient API error, an expired token or a rate limit does; FAKE_DEPLOYMENT_FAILS_AFTER
    # lets the first N calls through first, so the baseline read and the two mid-run fallback
    # reads can be failed independently (M1).
    if [[ -n "${FAKE_DEPLOYMENT_FAILS:-}" ]]; then
      n=$(cat "$FAKE_STATE/dep-list-calls" 2>/dev/null || echo 0)
      n=$((n + 1)); echo "$n" > "$FAKE_STATE/dep-list-calls"
      if (( n > ${FAKE_DEPLOYMENT_FAILS_AFTER:-0} )); then
        echo "error: failed to fetch deployments: unauthorized" >&2
        exit 1
      fi
    fi
    # The OLDEST row — already SUCCESS — comes FIRST, so a parser that reads element 0
    # instead of the newest by createdAt cannot pass the cases below.
    rows="$OLD_ROW"
    state="$FAKE_STATE/dep-$svc"
    if [[ -f "$state" ]]; then
      st=$(head -n 1 "$state")
      if [[ $(wc -l < "$state") -gt 1 ]]; then
        tail -n +2 "$state" > "$state.next" && mv "$state.next" "$state"
      fi
      rows="$rows,$(printf '{"id":"dep-%s","status":"%s","createdAt":"2026-09-07T10:00:00Z"}' "$svc" "$st")"
    fi
    # A CLI whose JSON carries no createdAt at all: the script must fail closed, not hang.
    [[ -n "${FAKE_NO_CREATED_AT:-}" ]] && rows=$(printf '%s' "$rows" | sed 's/,"createdAt":"[^"]*"//g')
    printf '[%s]\n' "$rows"
    ;;
esac
F
chmod +x "$tmp/railway"
export PATH="$tmp:$PATH"
export FAKE_PROJECT="Practice Match"
export SKIP_VERIFY=1
# Seconds, not minutes: the production bounds are 10 s / 120 s / 900 s.
export DEPLOY_POLL_INTERVAL=1
export DEPLOY_APPEAR_TIMEOUT=2
export DEPLOY_POLL_TIMEOUT=3

# Scratch repositories, made without touching the developer's git identity or signing config.
git_q() { git -c init.defaultBranch=main -c commit.gpgsign=false -c user.name=pm-test -c user.email=pm-test@example.invalid "$@"; }
# deploy.sh warns when HEAD is on no remote (L7); a remote-tracking ref makes a scratch
# checkout look pushed, so that warning appears only in the cases that are about it.
mark_pushed() { git_q -C "$1" update-ref refs/remotes/origin/deployed HEAD; }
new_repo() {  # new_repo <dir> <version>
  mkdir -p "$1"
  git_q -C "$1" init -q
  printf '[project]\nname = "practice-match"\nversion = "%s"\n' "$2" > "$1/pyproject.toml"
  printf 'FROM scratch\n' > "$1/Dockerfile"
  git_q -C "$1" add pyproject.toml Dockerfile
  git_q -C "$1" commit -q -m "scratch $2"
  mark_pushed "$1"
}

# --- 1. the upload is the committed tree: no .git, no untracked files -----------
repo="$tmp/main-checkout"; new_repo "$repo" 9.9.9
repo_sha=$(git_q -C "$repo" rev-parse --short HEAD)
echo "notes to self" > "$repo/scratch-note.txt"   # untracked: must not ship, must not refuse the deploy
reset_state; : > "$FAKE_LOG"
out=$(scripts/deploy.sh QA "$repo" 2>&1) || fail "a clean SOURCE_DIR must deploy; got: $out"
[[ "$out" != *"WARN"* ]] || fail "a pushed, attached, committed SOURCE_DIR must warn about nothing; got: $out"
grep -q '^UPLOAD_PYPROJECT version = "9.9.9"' "$FAKE_LOG" \
  || fail "the upload must carry SOURCE_DIR's committed pyproject.toml; got: $(grep '^UPLOAD_PYPROJECT' "$FAKE_LOG" || echo none)"
if grep -q '^UPLOAD_ENTRY \./\.git' "$FAKE_LOG"; then fail "the upload must not contain .git: $(grep '^UPLOAD_ENTRY \./\.git' "$FAKE_LOG")"; fi
if grep -q 'scratch-note.txt' "$FAKE_LOG"; then fail "the upload must not contain untracked files"; fi

# The path handed to `railway up` must be an extracted archive, not the checkout itself,
# and it must be gone once the script has exited.
upload_root=$(grep -m1 '^UPLOAD_ROOT ' "$FAKE_LOG" | cut -d' ' -f2-)
[[ -n "$upload_root" ]] || fail "railway up was not handed a directory to upload: $(cat "$FAKE_LOG")"
[[ "$upload_root" != "$repo" ]] || fail "railway up was handed the working directory itself, not an archive of HEAD"
[[ ! -e "$upload_root" ]] || fail "the temporary archive directory must be removed on exit; $upload_root still exists"

# --path-as-root is what makes the PATH argument the archive root; without it the CLI
# uses "the project directory" as the prefix instead — the resolution that shipped the
# wrong tree in the first place (railway up --help, CLI 5.26.0).
grep -q -- '--path-as-root' "$FAKE_LOG" || fail "railway up must pass --path-as-root; got: $(grep '^UP ' "$FAKE_LOG")"
[[ $(grep -c '^UP ' "$FAKE_LOG") -eq 2 ]] || fail "expected 2 railway up calls (api, worker); got: $(grep '^UP ' "$FAKE_LOG")"
grep -q -- "--environment QA --service api" "$FAKE_LOG" || fail "api not deployed to QA"
grep -q -- "--environment QA --service worker" "$FAKE_LOG" || fail "worker not deployed to QA"

# M2: the verifier defaults EXPECT_SHA/EXPECT_VERSION to ITS OWN checkout, so a hand-run
# after a SOURCE_DIR deploy would demand the wrong tree and fail a good deploy. deploy.sh
# must hand the operator the line that does not.
[[ "$out" == *"EXPECT_SHA=$repo_sha EXPECT_VERSION=9.9.9 scripts/verify-deploy.sh QA"* ]] \
  || fail "a successful deploy must echo the ready-to-paste re-verify line; got: $out"

# --- 2. BUILD_SHA travels inside the archive ------------------------------------
grep -q "^UPLOAD_BUILD_SHA $repo_sha$" "$FAKE_LOG" \
  || fail "BUILD_SHA must carry SOURCE_DIR's short HEAD ($repo_sha); got: $(grep '^UPLOAD_BUILD_SHA' "$FAKE_LOG" || echo none)"

# --- 3. an uncommitted tracked edit is refused (66), before the CLI is touched ---
reset_state; : > "$FAKE_LOG"
printf '[project]\nname = "practice-match"\nversion = "9.9.9-uncommitted"\n' > "$repo/pyproject.toml"
set +e
out=$(scripts/deploy.sh QA "$repo" 2>&1); code=$?
set -e
[[ $code -eq 66 ]] || fail "an uncommitted tracked edit must exit 66, got $code: $out"
[[ "$out" == *"pyproject.toml"* ]] || fail "the refusal must name the file that would be dropped; got: $out"
[[ ! -s "$FAKE_LOG" ]] || fail "a dirty SOURCE_DIR must be refused before the railway CLI is touched: $(cat "$FAKE_LOG")"
git_q -C "$repo" checkout -q -- pyproject.toml

# --- 4. a linked worktree as SOURCE_DIR archives the WORKTREE's HEAD ------------
# The P14 defect itself: `git archive` run with -C inside a worktree is worktree-correct,
# so the branch's tree is what ships — the main checkout's must not appear at all.
wt="$tmp/worktree-feat"
git_q -C "$repo" worktree add -q -b feat/browse-v3 "$wt"
[[ -f "$wt/.git" ]] || fail "the scratch worktree must use a .git pointer file (the P14 shape)"
printf '[project]\nname = "practice-match"\nversion = "8.8.8"\n' > "$wt/pyproject.toml"
git_q -C "$wt" add pyproject.toml
git_q -C "$wt" commit -q -m "branch-only version"
mark_pushed "$wt"
wt_sha=$(git_q -C "$wt" rev-parse --short HEAD)
[[ "$wt_sha" != "$repo_sha" ]] || fail "the worktree and the main checkout must differ for this case to mean anything"
reset_state; : > "$FAKE_LOG"
out=$(scripts/deploy.sh QA "$wt") || fail "a linked worktree must be deployable as SOURCE_DIR; got: $out"
grep -q '^UPLOAD_PYPROJECT version = "8.8.8"' "$FAKE_LOG" \
  || fail "SOURCE_DIR=<linked worktree> must upload the worktree's HEAD; got: $(grep '^UPLOAD_PYPROJECT' "$FAKE_LOG" || echo none)"
if grep -q '9\.9\.9' "$FAKE_LOG"; then fail "the main checkout's tree leaked into a worktree deploy — this is the P14 defect"; fi
grep -q "^UPLOAD_BUILD_SHA $wt_sha$" "$FAKE_LOG" \
  || fail "BUILD_SHA must be the worktree's sha ($wt_sha); got: $(grep '^UPLOAD_BUILD_SHA' "$FAKE_LOG" || echo none)"

# --- 5. a log-stream timeout after a good upload polls the NEW deployment to SUCCESS -
# The upload created a deployment newer than the one that was newest before `railway up`,
# so a non-zero `up` is only the log stream dying and the deploy must carry on.
reset_state; : > "$FAKE_LOG"
out=$(FAKE_UP_FAILS=1 FAKE_DEPLOY_STATUSES="BUILDING SUCCESS" scripts/deploy.sh QA "$repo" 2>&1) \
  || fail "a log-stream timeout after a successful upload must not abort the deploy; got: $out"
[[ "$out" == *"SUCCESS"* ]] || fail "the fallback must report the status it polled; got: $out"
grep -q '^railway deployment list --service api' "$FAKE_LOG" || fail "the fallback must poll deployment list for api"
grep -q '^railway deployment list --service worker' "$FAKE_LOG" || fail "the worker upload must still happen after the api log stream timed out"
[[ $(grep -c '^UP ' "$FAKE_LOG") -eq 2 ]] || fail "both services must still be uploaded; got: $(grep '^UP ' "$FAKE_LOG")"
# The baseline must be read BEFORE the upload, or "newer than what was there" means nothing.
first_api_call=$(grep -m1 -E '^railway (up|deployment list) .*--service api' "$FAKE_LOG")
[[ "$first_api_call" == railway\ deployment\ list* ]] \
  || fail "the newest deployment must be recorded BEFORE railway up, not after; first api call was: $first_api_call"

# --- 6. C2: an upload that created NO deployment fails closed (67) ---------------
# `railway up` can exit non-zero because the upload itself failed, in which case no new
# deployment exists and Railway's newest is still the previous deploy's SUCCESS. Polling
# for a status alone would read that SUCCESS and sail on with nothing deployed.
reset_state; : > "$FAKE_LOG"
set +e
out=$(FAKE_UP_FAILS=1 FAKE_UP_NO_DEPLOYMENT=1 scripts/deploy.sh QA "$repo" 2>&1); code=$?
set -e
[[ $code -eq 67 ]] || fail "an upload that created no deployment must exit 67, got $code: $out"
[[ "$out" == *"upload did not create a deployment for api"* ]] \
  || fail "the failure must say the upload created no deployment; got: $out"
[[ "$out" != *"SUCCESS"* ]] || fail "the previous deployment's SUCCESS must never be read as this deploy's; got: $out"
[[ $(grep -c '^UP ' "$FAKE_LOG") -eq 1 ]] || fail "the worker upload must not follow a failed api upload"
# It polled rather than giving up on the first look, and it stopped inside the bound.
[[ "$out" == *"waiting for the api deployment to appear"* ]] || fail "the appearance wait must poll and say so; got: $out"

# --- 7. C2: a deployment list with no createdAt fails closed too, never hangs ----
reset_state; : > "$FAKE_LOG"
set +e
out=$(FAKE_UP_FAILS=1 FAKE_NO_CREATED_AT=1 scripts/deploy.sh QA "$repo" 2>&1); code=$?
set -e
[[ $code -eq 67 ]] || fail "a deployment list without createdAt must exit 67, got $code: $out"
[[ "$out" == *"upload did not create a deployment for api"* ]] \
  || fail "a list with no createdAt must read as no new deployment; got: $out"

# --- 8. a FAILED deployment stops the deploy with 67 ----------------------------
reset_state; : > "$FAKE_LOG"
set +e
out=$(FAKE_UP_FAILS=1 FAKE_DEPLOY_STATUSES=FAILED scripts/deploy.sh QA "$repo" 2>&1); code=$?
set -e
[[ $code -eq 67 ]] || fail "a FAILED deployment must exit 67, got $code: $out"
[[ "$out" == *"FAILED"* ]] || fail "the failure must name the deployment status; got: $out"
[[ $(grep -c '^UP ' "$FAKE_LOG") -eq 1 ]] || fail "a failed api deployment must stop before the worker upload"

# --- 9. the settle wait is bounded: a deployment that never finishes exits 67 ----
reset_state; : > "$FAKE_LOG"
set +e
out=$(FAKE_UP_FAILS=1 FAKE_DEPLOY_STATUSES=BUILDING DEPLOY_POLL_TIMEOUT=0 scripts/deploy.sh QA "$repo" 2>&1); code=$?
set -e
[[ $code -eq 67 ]] || fail "an unsettled deployment must exit 67 within the bound, got $code: $out"
[[ "$out" == *"BUILDING"* ]] || fail "the bounded-wait failure must report the last status seen; got: $out"

# --- 10. the default SOURCE_DIR is the script's own repo root, and the verifier is
# handed the archived tree's sha and version ------------------------------------
# Proved with a scratch checkout that carries its own copy of deploy.sh (so the case is
# independent of this repository's working state) plus a recording stub where deploy.sh
# looks for the verifier — `scripts/verify-deploy.sh`, relative to its own repo root — so
# "continues to the worker and the verifier" is asserted without any network in play.
selfrepo="$tmp/self-checkout"; new_repo "$selfrepo" 7.7.7
mkdir -p "$selfrepo/scripts"
cp scripts/deploy.sh "$selfrepo/scripts/deploy.sh"
cat > "$selfrepo/scripts/verify-deploy.sh" <<'V'
#!/usr/bin/env bash
echo "VERIFY env=$1 EXPECT_SHA=${EXPECT_SHA:-} EXPECT_VERSION=${EXPECT_VERSION:-}" >> "$FAKE_LOG"
V
chmod +x "$selfrepo/scripts/verify-deploy.sh"
git_q -C "$selfrepo" add scripts/deploy.sh scripts/verify-deploy.sh
git_q -C "$selfrepo" commit -q -m "vendor deploy.sh and a recording verifier stub"
mark_pushed "$selfrepo"
self_sha=$(git_q -C "$selfrepo" rev-parse --short HEAD)
reset_state; : > "$FAKE_LOG"
out=$(SKIP_VERIFY= FAKE_UP_FAILS=1 FAKE_DEPLOY_STATUSES="BUILDING SUCCESS" "$selfrepo/scripts/deploy.sh" QA 2>&1) \
  || fail "the default SOURCE_DIR must deploy and reach the verifier; got: $out"
grep -q '^UPLOAD_PYPROJECT version = "7.7.7"' "$FAKE_LOG" \
  || fail "the default SOURCE_DIR must archive the script's own repo; got: $(grep '^UPLOAD_PYPROJECT' "$FAKE_LOG" || echo none)"
[[ $(grep -c '^UP ' "$FAKE_LOG") -eq 2 ]] || fail "the worker upload must follow the api's recovered log-stream timeout"
grep -q "^VERIFY env=QA EXPECT_SHA=$self_sha EXPECT_VERSION=7.7.7$" "$FAKE_LOG" \
  || fail "the verifier must be handed the archived tree's sha and version; got: $(grep '^VERIFY' "$FAKE_LOG" || echo none)"

# --- 11. a SOURCE_DIR that is not a git working tree is a usage error (64) ------
mkdir -p "$tmp/not-a-repo"
reset_state; : > "$FAKE_LOG"
set +e
out=$(scripts/deploy.sh QA "$tmp/not-a-repo" 2>&1); code=$?
set -e
[[ $code -eq 64 ]] || fail "a SOURCE_DIR that is not a git working tree must exit 64, got $code: $out"
[[ ! -s "$FAKE_LOG" ]] || fail "an unusable SOURCE_DIR must be refused before the railway CLI is touched: $(cat "$FAKE_LOG")"

# --- 12. M1: a baseline `deployment list` failure warns loudly and does NOT block a deploy -
# The baseline read is on the happy path, so a CLI blip must not become a silent abort: it
# degrades to an empty baseline (safe — an unreadable list then fails phase 1 closed anyway)
# and says so, with the CLI's own reason visible rather than swallowed by 2>/dev/null.
reset_state; : > "$FAKE_LOG"
out=$(FAKE_DEPLOYMENT_FAILS=1 scripts/deploy.sh QA "$repo" 2>&1) \
  || fail "a deployment-list failure must not block a deploy whose upload succeeded; got: $out"
[[ "$out" == *"WARN: could not read api's deployment list"* ]] || fail "the degraded baseline must warn; got: $out"
[[ "$out" == *"unauthorized"* ]] || fail "the CLI's own reason must reach the operator, not /dev/null; got: $out"
[[ $(grep -c '^UP ' "$FAKE_LOG") -eq 2 ]] || fail "both services must still be uploaded; got: $(grep '^UP ' "$FAKE_LOG")"

# --- 13. M1: mid-run (phase 1) a deployment-list failure fails closed, reason visible ------
reset_state; : > "$FAKE_LOG"
set +e
out=$(FAKE_UP_FAILS=1 FAKE_DEPLOYMENT_FAILS=1 FAKE_DEPLOYMENT_FAILS_AFTER=1 scripts/deploy.sh QA "$repo" 2>&1); code=$?
set -e
[[ $code -eq 67 ]] || fail "a deployment-list failure during the fallback must fail closed with 67, got $code: $out"
[[ "$out" == *"unauthorized"* ]] || fail "the CLI's failure must be printed before failing closed; got: $out"

# --- 14. M1: and in phase 2, after the deployment has been identified ---------------------
reset_state; : > "$FAKE_LOG"
set +e
out=$(FAKE_UP_FAILS=1 FAKE_DEPLOY_STATUSES="BUILDING SUCCESS" FAKE_DEPLOYMENT_FAILS=1 FAKE_DEPLOYMENT_FAILS_AFTER=2 scripts/deploy.sh QA "$repo" 2>&1); code=$?
set -e
[[ $code -eq 67 ]] || fail "losing the deployment list mid-settle must fail closed with 67, got $code: $out"
[[ "$out" == *"unauthorized"* ]] || fail "the CLI's failure must be printed before failing closed; got: $out"

# --- 15. L1: a bare repository is not a working tree — 64, not git's exit 128 ------------
# `rev-parse --git-dir` SUCCEEDS for a bare repo and for a `.git` directory (both print
# is-inside-work-tree=false, rc 0), so the guard has to read the answer, not the exit code.
git_q -C "$tmp" init -q --bare bare-repo.git
reset_state; : > "$FAKE_LOG"
set +e
out=$(scripts/deploy.sh QA "$tmp/bare-repo.git" 2>&1); code=$?
set -e
[[ $code -eq 64 ]] || fail "a bare repository must exit 64, got $code: $out"
[[ "$out" == *"not a git working tree"* ]] || fail "the bare-repo refusal must use the working-tree message; got: $out"
[[ ! -s "$FAKE_LOG" ]] || fail "a bare repository must be refused before the railway CLI is touched"

# --- 16. L1: a `.git` directory is not a working tree either -----------------------------
reset_state; : > "$FAKE_LOG"
set +e
out=$(scripts/deploy.sh QA "$repo/.git" 2>&1); code=$?
set -e
[[ $code -eq 64 ]] || fail "a .git directory must exit 64, got $code: $out"
[[ "$out" == *"not a git working tree"* ]] || fail "the .git-directory refusal must use the working-tree message; got: $out"

# --- 17. L2: a repository with no commits — 64, not git's 'Needed a single revision' 128 --
mkdir -p "$tmp/no-commits"; git_q -C "$tmp/no-commits" init -q
reset_state; : > "$FAKE_LOG"
set +e
out=$(scripts/deploy.sh QA "$tmp/no-commits" 2>&1); code=$?
set -e
[[ $code -eq 64 ]] || fail "a repository with no commits must exit 64, got $code: $out"
[[ "$out" == *"no commits"* ]] || fail "the empty-repo refusal must name the reason; got: $out"
[[ "$out" != *"Needed a single revision"* ]] || fail "git's own fatal must not be what the operator sees; got: $out"
[[ ! -s "$FAKE_LOG" ]] || fail "an empty repository must be refused before the railway CLI is touched"

# --- 18. L3: an archived tree with no pyproject.toml fails on one clean line ---------------
nopy="$tmp/no-pyproject"; mkdir -p "$nopy"
git_q -C "$nopy" init -q
printf 'FROM scratch\n' > "$nopy/Dockerfile"
git_q -C "$nopy" add Dockerfile
git_q -C "$nopy" commit -q -m "no pyproject"
mark_pushed "$nopy"
reset_state; : > "$FAKE_LOG"
set +e
out=$(scripts/deploy.sh QA "$nopy" 2>&1); code=$?
set -e
[[ $code -eq 64 ]] || fail "a tree without pyproject.toml must exit 64, got $code: $out"
[[ "$out" == *"pyproject.toml"* ]] || fail "the failure must name pyproject.toml; got: $out"
[[ "$out" != *"Traceback"* ]] || fail "a missing pyproject must be one clean line, not a Python traceback; got: $out"
[[ $(grep -c '^UP ' "$FAKE_LOG") -eq 0 ]] || fail "nothing may be uploaded when the version cannot be read"

# --- 19. L7: HEAD on no remote warns, and still deploys ----------------------------------
# The stamp is the point: a BUILD_SHA nobody else can fetch defeats it. A warning, never a
# refusal — John deploys from a worktree before pushing all the time.
local_only="$tmp/local-only"; new_repo "$local_only" 5.5.5
git_q -C "$local_only" update-ref -d refs/remotes/origin/deployed
reset_state; : > "$FAKE_LOG"
out=$(scripts/deploy.sh QA "$local_only" 2>&1) || fail "an unpushed HEAD must still deploy; got: $out"
[[ "$out" == *"is not on any remote"* ]] || fail "an unpushed HEAD must warn; got: $out"
[[ "$out" == *"push before deploying"* ]] || fail "the warning must say what to do; got: $out"
[[ $(grep -c '^UP ' "$FAKE_LOG") -eq 2 ]] || fail "the warning must not stop the deploy"

# --- 20. L7: a detached HEAD warns, and still deploys ------------------------------------
detached="$tmp/detached"; new_repo "$detached" 4.4.4
git_q -C "$detached" checkout -q --detach
reset_state; : > "$FAKE_LOG"
out=$(scripts/deploy.sh QA "$detached" 2>&1) || fail "a detached HEAD must still deploy; got: $out"
[[ "$out" == *"detached HEAD"* ]] || fail "a detached HEAD must be called out; got: $out"
[[ $(grep -c '^UP ' "$FAKE_LOG") -eq 2 ]] || fail "the detached-HEAD warning must not stop the deploy"

echo "deploy archive OK"
