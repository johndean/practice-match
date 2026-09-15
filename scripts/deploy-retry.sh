#!/usr/bin/env bash
# Deploy through scripts/deploy.sh, retrying the one failure this project actually sees.
#
# WHY THIS EXISTS, measured 2026-09-16. Deploys failed six times in a day with the same
# shape: `railway up` reaches "Uploading...", the request to backboard.railway.com dies with
# "operation timed out", Railway records a deployment anyway, and that deployment sits
# INITIALIZING with no code to build until it reports "Failed to create code snapshot".
#
# Root cause is the upload, not Railway and not the tree. Measured upstream bandwidth from
# the build machine that day: 15 KB/s for a completed 2 MB POST, 47 KB/s for 8 MB. The
# committed archive is ~22 MB after .railwayignore is applied, so the upload needs between
# eight and twenty-five minutes of sustained throughput and the client gives up first. Three
# other hypotheses were tested and refuted before this one: halving the payload (42 MB -> 22 MB)
# changed nothing, the CLI upgrade 5.26.0 -> 5.57.2 changed nothing, and an apparent 717 KB/s
# to Railway turned out to be a 413 refusal after 720 KB rather than a completed upload.
#
# So: retry, on a long bound, and say plainly what is happening between attempts. This does
# NOT bypass deploy.sh -- every guard, the 🚦 project check, the committed-tree archive and
# the post-deploy verification all still run, once per attempt.
#
# usage: scripts/deploy-retry.sh QA|production [SOURCE_DIR]
#        ATTEMPTS=3 DEPLOY_POLL_TIMEOUT=1800 scripts/deploy-retry.sh QA
set -uo pipefail

ENV_NAME="${1:-}"
case "$ENV_NAME" in
  QA|production) ;;
  *) echo "usage: $0 QA|production [SOURCE_DIR]" >&2; exit 64 ;;
esac
SOURCE_DIR="${2:-}"
ATTEMPTS="${ATTEMPTS:-3}"
export DEPLOY_POLL_TIMEOUT="${DEPLOY_POLL_TIMEOUT:-1800}"

here=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
src="${SOURCE_DIR:-$here}"

# What is about to go over the wire, and what that costs at the measured rate. An operator
# who knows it is a twenty-minute upload does not kill it at minute five.
if [[ -d "$src/.git" || -f "$src/.git" ]]; then
  bytes=$(git -C "$src" archive --format=tar HEAD 2>/dev/null | wc -c | tr -d ' ')
  if [[ -n "$bytes" && "$bytes" -gt 0 ]]; then
    mb=$(( bytes / 1048576 ))
    echo "→ archive of $(git -C "$src" rev-parse --short HEAD) is ~${mb} MB before .railwayignore is applied"
    echo "  at 15-47 KB/s that is roughly $(( mb * 1024 / 47 / 60 ))-$(( mb * 1024 / 15 / 60 )) minutes of upload per service"
  fi
fi

for attempt in $(seq 1 "$ATTEMPTS"); do
  echo
  echo "=== attempt $attempt of $ATTEMPTS — $(date -u '+%H:%M:%SZ') ==="
  if [[ -n "$SOURCE_DIR" ]]; then
    "$here/scripts/deploy.sh" "$ENV_NAME" "$SOURCE_DIR"
  else
    "$here/scripts/deploy.sh" "$ENV_NAME"
  fi
  code=$?
  if [[ $code -eq 0 ]]; then
    echo
    echo "✓ deployed to $ENV_NAME on attempt $attempt"
    exit 0
  fi
  # 64-66 are deploy.sh's own refusals: a bad argument, a dirty tree, an unreadable version.
  # Retrying those repeats a mistake rather than a timeout, so stop and let the operator fix it.
  if [[ $code -ge 64 && $code -le 66 ]]; then
    echo "STOP: deploy.sh refused this deploy (exit $code). That is not a transient; fix it and re-run." >&2
    exit "$code"
  fi
  echo "  attempt $attempt failed (exit $code)" >&2
  if [[ $attempt -lt $ATTEMPTS ]]; then
    # Configurable so the shell suite does not pay a real minute per case; a deploy run by
    # hand should leave it alone, because retrying a slow upload instantly just contends.
    pause="${DEPLOY_RETRY_SLEEP:-60}"
    [[ "$pause" -gt 0 ]] && echo "  waiting ${pause}s before the next attempt — Railway keeps the previous deployment serving meanwhile" >&2
    sleep "$pause"
  fi
done

echo >&2
echo "STOP: $ATTEMPTS attempts failed. Nothing was taken down: the previous deployment keeps serving." >&2
echo "  If every attempt died at 'Uploading... operation timed out', the upload is the problem, not the code." >&2
echo "  Check upstream bandwidth from this machine before trying again:" >&2
echo "    dd if=/dev/zero bs=1m count=2 | curl -s -o /dev/null -w '%{speed_upload} B/s\\n' --data-binary @- https://httpbin.org/post" >&2
echo "  Below ~100 KB/s a 22 MB archive will not finish. Deploy from a faster connection." >&2
exit 67
