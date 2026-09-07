#!/usr/bin/env bash
# Deploy to one Railway environment. Guards John's standing rule: read `railway status`
# back and refuse unless the linked project is Practice Match — this machine runs
# several Railway projects and `railway up` ships to whatever is linked.
#
# The guard is not theoretical: ~/.railway/config.json links $HOME itself, and the
# CLI resolves a project by walking up the tree, so an unlinked directory anywhere
# under /Users/johndean inherits that project. Without this check `railway up` from
# a fresh clone would deploy this repo over an unrelated production service.
#
# usage: deploy.sh QA|production [SOURCE_DIR]      SOURCE_DIR defaults to this repo root
#
# What is uploaded is `git archive HEAD` of SOURCE_DIR, extracted into a temp directory —
# never a working directory, and never a tree the CLI resolved for itself. P14, measured
# 2026-09-07: run from the linked worktree `.worktrees/feat-browse-v3` (HEAD 17f40c3),
# `railway up` (CLI 5.26.0) followed that worktree's `.git` *pointer file* back to the main
# repository directory and uploaded MAIN's tree, while /api/healthz reported the branch's
# sha — the COMMIT_SHA variable this script had just set. So: name the source explicitly,
# archive its HEAD, and hand the CLI a plain directory with no `.git` to mis-resolve.
# To deploy a branch: `scripts/deploy.sh QA .worktrees/<branch>`.
#
# Exit codes: 64 usage (bad environment, or a SOURCE_DIR that is not a git working tree)
#             65 the linked Railway project is not Practice Match (the 🚦 guard)
#             66 SOURCE_DIR has uncommitted changes to tracked files
#             67 the deployment did not reach SUCCESS
set -euo pipefail
ENV="${1:-}"
[[ "$ENV" == "QA" || "$ENV" == "production" ]] || { echo "usage: $0 QA|production [SOURCE_DIR]" >&2; exit 64; }
# Resolved before the cd below, so a relative SOURCE_DIR means what the caller typed.
if [[ -n "${2:-}" ]]; then
  SOURCE_DIR=$(cd "$2" 2>/dev/null && pwd) || { echo "STOP: SOURCE_DIR '$2' is not a directory" >&2; exit 64; }
fi
cd "$(dirname "$0")/.."
SOURCE_DIR="${SOURCE_DIR:-$PWD}"
git -C "$SOURCE_DIR" rev-parse --git-dir >/dev/null 2>&1 \
  || { echo "STOP: SOURCE_DIR '$SOURCE_DIR' is not a git working tree; deploy.sh uploads a git archive of its HEAD" >&2; exit 64; }
# Untracked files are fine (they are not in HEAD and will not ship). Uncommitted edits to
# TRACKED files are not: "deploy what is committed" would silently drop them, which is a
# worse surprise than refusing.
DIRTY=$(git -C "$SOURCE_DIR" status --porcelain --untracked-files=no)
if [[ -n "$DIRTY" ]]; then
  echo "STOP: '$SOURCE_DIR' has uncommitted changes to tracked files. deploy.sh uploads the committed tree (HEAD), so these would NOT ship:" >&2
  echo "$DIRTY" >&2
  echo "Commit them (or pass a SOURCE_DIR that is committed) and run again." >&2
  exit 66
fi
PROJECT=$(railway status --json | python3 -c 'import sys,json; print(json.load(sys.stdin).get("name",""))')
if [[ "$PROJECT" != "Practice Match" ]]; then
  echo "🚦 STOP: railway is linked to '${PROJECT:-nothing}', not 'Practice Match'. Fix with: railway link" >&2
  exit 65
fi
echo "🚦 railway status → Project: $PROJECT | target environment: $ENV"
SHA=$(git -C "$SOURCE_DIR" rev-parse --short HEAD)
TMP=$(mktemp -d "${TMPDIR:-/tmp}/practice-match-deploy.XXXXXX")
trap 'rm -rf "$TMP"' EXIT
git -C "$SOURCE_DIR" archive --format=tar HEAD | tar -x -C "$TMP"
# The artefact's own commit, read back by /api/healthz in preference to COMMIT_SHA: a
# variable can be set without the uploaded tree ever changing (that is exactly how P14
# hid itself), a file inside the archive cannot.
printf '%s\n' "$SHA" > "$TMP/BUILD_SHA"
# Read from the archive, not the checkout: this is definitionally the version being shipped.
VERSION=$(python3 -c 'import sys,tomllib; print(tomllib.load(open(sys.argv[1],"rb"))["project"]["version"])' "$TMP/pyproject.toml")
echo "→ uploading the committed tree of $SOURCE_DIR (HEAD $SHA, version $VERSION)"

# `railway up --ci` streams build logs, and that stream can time out with a
# `reqwest error … operation timed out` *after* the upload succeeded — the deployment
# carries on to SUCCESS regardless (measured 2026-09-07). Aborting there would leave the
# api deployed and the worker not, so a non-zero `up` is resolved by asking Railway what
# actually happened rather than by guessing.
newest_deployment_status() {
  railway deployment list --service "$1" --environment "$2" --json 2>/dev/null | python3 -c '
import json, sys


def rows(payload):
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []


try:
    found = rows(json.load(sys.stdin))
except Exception:
    found = []
if not found:
    print("UNKNOWN")
    raise SystemExit(0)
found.sort(key=lambda r: str(r.get("createdAt") or r.get("created_at") or ""), reverse=True)
print(str(found[0].get("status") or "UNKNOWN").upper())
'
}
await_deployment() {
  local svc="$1" env="$2" interval="${DEPLOY_POLL_INTERVAL:-10}" timeout="${DEPLOY_POLL_TIMEOUT:-900}" waited=0 status
  if (( interval < 1 )); then interval=1; fi
  while :; do
    status=$(newest_deployment_status "$svc" "$env")
    case "$status" in
      SUCCESS)
        echo "   $svc deployment status → SUCCESS (the upload completed; only the log stream failed)"
        return 0 ;;
      FAILED|CRASHED)
        echo "STOP: the $svc deployment for $env ended $status. Logs: railway logs --service $svc --environment $env --lines 100" >&2
        exit 67 ;;
    esac
    if (( waited >= timeout )); then
      echo "STOP: the $svc deployment for $env was still $status after ${waited}s (bound ${timeout}s); not calling that a good deploy" >&2
      exit 67
    fi
    echo "   $svc deployment status → $status (waited ${waited}s of ${timeout}s)"
    sleep "$interval"
    waited=$(( waited + interval ))
  done
}

for svc in api worker; do
  railway variable set "COMMIT_SHA=$SHA" --service "$svc" --environment "$ENV" --skip-deploys >/dev/null
  echo "→ railway up $TMP --path-as-root --environment $ENV --service $svc --ci  (commit $SHA)"
  # --path-as-root: without it the PATH argument is filtered against "the project
  # directory" the CLI resolves for itself, which is the mis-resolution P14 was.
  if ! railway up "$TMP" --path-as-root --environment "$ENV" --service "$svc" --ci; then
    echo "   railway up exited non-zero (the log stream times out after a good upload); asking Railway for the deployment status" >&2
    await_deployment "$svc" "$ENV"
  fi
done
[[ -n "${SKIP_VERIFY:-}" ]] || EXPECT_SHA="$SHA" EXPECT_VERSION="$VERSION" scripts/verify-deploy.sh "$ENV"
