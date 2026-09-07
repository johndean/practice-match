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
# records a manifest of the directory `railway up` was handed, so the assertions can
# inspect exactly what would have been uploaded. Scratch git repositories — including a
# real `git worktree add`, so the `.git` pointer file is the genuine article — stand in
# for the checkouts. Nothing here touches the network or a Railway account.
set -euo pipefail; cd "$(dirname "$0")/../.."
fail() { echo "FAIL: $*"; exit 1; }
[[ -x scripts/deploy.sh ]] || fail "scripts/deploy.sh missing or not executable"

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
export FAKE_LOG="$tmp/log"; : > "$FAKE_LOG"
export FAKE_STATUS_FILE="$tmp/deployment-status"; printf 'SUCCESS\n' > "$FAKE_STATUS_FILE"

cat > "$tmp/railway" <<'F'
#!/usr/bin/env bash
echo "railway $*" >> "$FAKE_LOG"
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
    # The measured failure mode: the upload succeeds, then the CLI's own log stream
    # times out and `up` exits non-zero ("reqwest error … operation timed out") while
    # the deployment carries on to SUCCESS.
    [[ -n "${FAKE_UP_FAILS:-}" ]] && { echo "reqwest error: error sending request: operation timed out" >&2; exit 1; }
    exit 0
    ;;
  deployment)
    # `deployment list --json`. The OLDEST row comes first and is already SUCCESS, so a
    # parser that reads element 0 rather than the newest by createdAt would sail past
    # the FAILED case below — this ordering is the assertion. One status per line in
    # FAKE_STATUS_FILE, popped per call; the last line repeats for ever.
    st=$(head -n 1 "$FAKE_STATUS_FILE")
    if [[ $(wc -l < "$FAKE_STATUS_FILE") -gt 1 ]]; then
      tail -n +2 "$FAKE_STATUS_FILE" > "$FAKE_STATUS_FILE.next" && mv "$FAKE_STATUS_FILE.next" "$FAKE_STATUS_FILE"
    fi
    printf '[{"id":"dep-old","status":"SUCCESS","createdAt":"2026-09-07T09:00:00Z"},{"id":"dep-new","status":"%s","createdAt":"2026-09-07T10:00:00Z"}]\n' "$st"
    ;;
esac
F
chmod +x "$tmp/railway"
export PATH="$tmp:$PATH"
export FAKE_PROJECT="Practice Match"
export SKIP_VERIFY=1
export DEPLOY_POLL_INTERVAL=1

# Scratch repositories, made without touching the developer's git identity or signing config.
git_q() { git -c init.defaultBranch=main -c commit.gpgsign=false -c user.name=pm-test -c user.email=pm-test@example.invalid "$@"; }
new_repo() {  # new_repo <dir> <version>
  mkdir -p "$1"
  git_q -C "$1" init -q
  printf '[project]\nname = "practice-match"\nversion = "%s"\n' "$2" > "$1/pyproject.toml"
  printf 'FROM scratch\n' > "$1/Dockerfile"
  git_q -C "$1" add pyproject.toml Dockerfile
  git_q -C "$1" commit -q -m "scratch $2"
}

# --- 1. the upload is the committed tree: no .git, no untracked files -----------
repo="$tmp/main-checkout"; new_repo "$repo" 9.9.9
echo "notes to self" > "$repo/scratch-note.txt"   # untracked: must not ship, must not refuse the deploy
: > "$FAKE_LOG"
out=$(scripts/deploy.sh QA "$repo") || fail "a clean SOURCE_DIR must deploy; got: $out"
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

# --- 2. BUILD_SHA travels inside the archive ------------------------------------
repo_sha=$(git_q -C "$repo" rev-parse --short HEAD)
grep -q "^UPLOAD_BUILD_SHA $repo_sha$" "$FAKE_LOG" \
  || fail "BUILD_SHA must carry SOURCE_DIR's short HEAD ($repo_sha); got: $(grep '^UPLOAD_BUILD_SHA' "$FAKE_LOG" || echo none)"

# --- 3. an uncommitted tracked edit is refused (66), before the CLI is touched ---
: > "$FAKE_LOG"
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
wt_sha=$(git_q -C "$wt" rev-parse --short HEAD)
[[ "$wt_sha" != "$repo_sha" ]] || fail "the worktree and the main checkout must differ for this case to mean anything"
: > "$FAKE_LOG"
out=$(scripts/deploy.sh QA "$wt") || fail "a linked worktree must be deployable as SOURCE_DIR; got: $out"
grep -q '^UPLOAD_PYPROJECT version = "8.8.8"' "$FAKE_LOG" \
  || fail "SOURCE_DIR=<linked worktree> must upload the worktree's HEAD; got: $(grep '^UPLOAD_PYPROJECT' "$FAKE_LOG" || echo none)"
if grep -q '9\.9\.9' "$FAKE_LOG"; then fail "the main checkout's tree leaked into a worktree deploy — this is the P14 defect"; fi
grep -q "^UPLOAD_BUILD_SHA $wt_sha$" "$FAKE_LOG" \
  || fail "BUILD_SHA must be the worktree's sha ($wt_sha); got: $(grep '^UPLOAD_BUILD_SHA' "$FAKE_LOG" || echo none)"

# --- 5. a log-stream timeout after a good upload polls through to SUCCESS -------
: > "$FAKE_LOG"; printf 'BUILDING\nSUCCESS\n' > "$FAKE_STATUS_FILE"
out=$(FAKE_UP_FAILS=1 scripts/deploy.sh QA "$repo" 2>&1) \
  || fail "a log-stream timeout after a successful upload must not abort the deploy; got: $out"
[[ "$out" == *"SUCCESS"* ]] || fail "the fallback must report the status it polled; got: $out"
grep -q '^railway deployment list --service api' "$FAKE_LOG" || fail "the fallback must poll deployment list for api"
grep -q '^railway deployment list --service worker' "$FAKE_LOG" || fail "the worker upload must still happen after the api log stream timed out"
[[ $(grep -c '^UP ' "$FAKE_LOG") -eq 2 ]] || fail "both services must still be uploaded; got: $(grep '^UP ' "$FAKE_LOG")"

# --- 6. a FAILED deployment stops the deploy with 67 ----------------------------
: > "$FAKE_LOG"; printf 'FAILED\n' > "$FAKE_STATUS_FILE"
set +e
out=$(FAKE_UP_FAILS=1 scripts/deploy.sh QA "$repo" 2>&1); code=$?
set -e
[[ $code -eq 67 ]] || fail "a FAILED deployment must exit 67, got $code: $out"
[[ "$out" == *"FAILED"* ]] || fail "the failure must name the deployment status; got: $out"
[[ $(grep -c '^UP ' "$FAKE_LOG") -eq 1 ]] || fail "a failed api deployment must stop before the worker upload"

# --- 7. the wait is bounded: a deployment that never settles exits 67, never hangs -
: > "$FAKE_LOG"; printf 'BUILDING\n' > "$FAKE_STATUS_FILE"
set +e
out=$(FAKE_UP_FAILS=1 DEPLOY_POLL_TIMEOUT=0 scripts/deploy.sh QA "$repo" 2>&1); code=$?
set -e
[[ $code -eq 67 ]] || fail "an unsettled deployment must exit 67 within the bound, got $code: $out"
[[ "$out" == *"BUILDING"* ]] || fail "the bounded-wait failure must report the last status seen; got: $out"

# --- 8. the default SOURCE_DIR is the script's own repo root --------------------
# Proved with a scratch checkout that carries its own copy of deploy.sh, so the case is
# independent of this repository's working state.
selfrepo="$tmp/self-checkout"; new_repo "$selfrepo" 7.7.7
mkdir -p "$selfrepo/scripts"
cp scripts/deploy.sh "$selfrepo/scripts/deploy.sh"
git_q -C "$selfrepo" add scripts/deploy.sh
git_q -C "$selfrepo" commit -q -m "vendor deploy.sh"
: > "$FAKE_LOG"; printf 'SUCCESS\n' > "$FAKE_STATUS_FILE"
out=$("$selfrepo/scripts/deploy.sh" QA) || fail "the default SOURCE_DIR must be the script's own repo root; got: $out"
grep -q '^UPLOAD_PYPROJECT version = "7.7.7"' "$FAKE_LOG" \
  || fail "the default SOURCE_DIR must archive the script's own repo; got: $(grep '^UPLOAD_PYPROJECT' "$FAKE_LOG" || echo none)"

# --- 9. a SOURCE_DIR that is not a git working tree is a usage error (64) -------
mkdir -p "$tmp/not-a-repo"
: > "$FAKE_LOG"
set +e
out=$(scripts/deploy.sh QA "$tmp/not-a-repo" 2>&1); code=$?
set -e
[[ $code -eq 64 ]] || fail "a SOURCE_DIR that is not a git working tree must exit 64, got $code: $out"
[[ ! -s "$FAKE_LOG" ]] || fail "an unusable SOURCE_DIR must be refused before the railway CLI is touched: $(cat "$FAKE_LOG")"

echo "deploy archive OK"
