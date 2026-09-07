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
#             67 the upload created no deployment, or the deployment did not reach SUCCESS
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
#
# It must fail CLOSED, though: `up` also exits non-zero when the upload itself failed, and
# then no new deployment exists and Railway's newest is still the PREVIOUS deploy — very
# possibly a SUCCESS, which a status-only poll would read as this deploy succeeding
# (C2 ruling, 2026-09-07). So the newest deployment is recorded before the upload and only
# a strictly newer one counts. A deployment with no `createdAt` cannot be dated, so it
# reads as "no new deployment" rather than being trusted or waited on for ever.
#
# select_deployment <svc> <env> <baseline-createdAt> [dep-id] [dep-createdAt]
# Prints "<createdAt>\t<id>\t<STATUS>" for the deployment being tracked, or nothing:
# with dep-id/dep-createdAt it is that exact deployment, otherwise the newest one whose
# createdAt is strictly after the baseline. Rows without a createdAt are dropped.
select_deployment() {
  railway deployment list --service "$1" --environment "$2" --json 2>/dev/null |
    BASELINE="$3" DEP_ID="${4:-}" DEP_CREATED="${5:-}" python3 -c '
import json, os, sys


def rows(payload):
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []


def created(row):
    return str(row.get("createdAt") or row.get("created_at") or "")


try:
    found = [r for r in rows(json.load(sys.stdin)) if created(r)]
except Exception:
    found = []
want_id, want_created, baseline = os.environ["DEP_ID"], os.environ["DEP_CREATED"], os.environ["BASELINE"]
if want_id:
    found = [r for r in found if str(r.get("id") or "") == want_id]
elif want_created:
    found = [r for r in found if created(r) == want_created]
else:
    found = [r for r in found if created(r) > baseline]
if found:
    found.sort(key=created, reverse=True)
    top = found[0]
    print(created(top), str(top.get("id") or ""), str(top.get("status") or "UNKNOWN").upper(), sep="\t")
'
}

# await_deployment <svc> <env> <baseline-createdAt>
await_deployment() {
  local svc="$1" env="$2" baseline="$3"
  local interval="${DEPLOY_POLL_INTERVAL:-10}"
  local appear="${DEPLOY_APPEAR_TIMEOUT:-120}"
  local settle="${DEPLOY_POLL_TIMEOUT:-900}"
  if (( interval < 1 )); then interval=1; fi
  local waited=0 row status dep_id dep_created
  # Phase 1 — the upload must have created a deployment newer than the baseline.
  while :; do
    row=$(select_deployment "$svc" "$env" "$baseline")
    if [[ -n "$row" ]]; then
      dep_created=$(printf '%s' "$row" | cut -f1)
      dep_id=$(printf '%s' "$row" | cut -f2)
      break
    fi
    if (( waited >= appear )); then
      echo "STOP: upload did not create a deployment for $svc in $env — nothing newer than '${baseline:-<no previous deployment>}' after ${waited}s (bound ${appear}s). The upload itself failed; nothing was deployed." >&2
      exit 67
    fi
    echo "   waiting for the $svc deployment to appear (${waited}s of ${appear}s)"
    sleep "$interval"
    waited=$(( waited + interval ))
  done
  echo "   $svc deployment ${dep_id:-$dep_created} was created by the upload; waiting for it to settle"
  # Phase 2 — that deployment, and only that one, must reach SUCCESS within the bound.
  waited=0
  while :; do
    row=$(select_deployment "$svc" "$env" "$baseline" "$dep_id" "$dep_created")
    status=$(printf '%s' "$row" | cut -f3)
    case "$status" in
      SUCCESS)
        echo "   $svc deployment status → SUCCESS (the upload completed; only the log stream failed)"
        return 0 ;;
      FAILED|CRASHED)
        echo "STOP: the $svc deployment for $env ended $status. Logs: railway logs --service $svc --environment $env --lines 100" >&2
        exit 67 ;;
    esac
    if (( waited >= settle )); then
      echo "STOP: the $svc deployment for $env was still ${status:-UNKNOWN} after ${waited}s (bound ${settle}s); not calling that a good deploy" >&2
      exit 67
    fi
    echo "   $svc deployment status → ${status:-UNKNOWN} (waited ${waited}s of ${settle}s)"
    sleep "$interval"
    waited=$(( waited + interval ))
  done
}

for svc in api worker; do
  railway variable set "COMMIT_SHA=$SHA" --service "$svc" --environment "$ENV" --skip-deploys >/dev/null
  # Recorded BEFORE the upload: this is the only evidence that can tell a dead log stream
  # from an upload that never happened.
  BASELINE=$(select_deployment "$svc" "$ENV" "" | cut -f1)
  echo "→ railway up $TMP --path-as-root --environment $ENV --service $svc --ci  (commit $SHA)"
  # --path-as-root: without it the PATH argument is filtered against "the project
  # directory" the CLI resolves for itself, which is the mis-resolution P14 was.
  if ! railway up "$TMP" --path-as-root --environment "$ENV" --service "$svc" --ci; then
    echo "   railway up exited non-zero (the log stream times out after a good upload); asking Railway for the deployment status" >&2
    await_deployment "$svc" "$ENV" "$BASELINE"
  fi
done
[[ -n "${SKIP_VERIFY:-}" ]] || EXPECT_SHA="$SHA" EXPECT_VERSION="$VERSION" scripts/verify-deploy.sh "$ENV"
