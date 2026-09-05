#!/usr/bin/env bash
# Post-deploy probes. Usage: verify-deploy.sh QA|production [BASE_URL]
# BASE_URL defaults to the environment's custom domain; pass the *.up.railway.app
# URL (or set VERIFY_BASE_URL) before DNS is live.
#
# EXPECT_SHA defaults to this checkout's HEAD: the point of the probe is to prove
# the code now serving traffic is the code we just deployed, so a stale container
# that answers 200 with an older commit_sha must fail the deploy.
set -euo pipefail
ENV="${1:?usage: verify-deploy.sh QA|production [BASE_URL]}"
case "$ENV" in
  QA)         DEFAULT_BASE="https://qa.foundation.vin"; WANT=qa ;;
  production) DEFAULT_BASE="https://foundation.vin";    WANT=production ;;
  *) echo "usage: verify-deploy.sh QA|production [BASE_URL]" >&2; exit 64 ;;
esac
BASE="${2:-${VERIFY_BASE_URL:-$DEFAULT_BASE}}"
BASE="${BASE%/}"
EXPECT_SHA="${EXPECT_SHA:-$(git rev-parse --short HEAD 2>/dev/null || true)}"

echo "→ GET $BASE/api/healthz"
# Piped, not process-substituted, so pipefail propagates a curl failure (-sf exits
# non-zero on 4xx/5xx) instead of handing python an empty body.
curl -sf --max-time 20 "$BASE/api/healthz" | WANT="$WANT" EXPECT_SHA="$EXPECT_SHA" python3 -c '
import os, sys, json
b = json.load(sys.stdin)
want, expect = os.environ["WANT"], os.environ["EXPECT_SHA"]
got = b["environment"]
assert got == want, f"environment is {got!r}, expected {want!r}: {b}"
assert b["db"]["ok"] and b["redis"]["ok"], b
sha = b["commit_sha"]
if expect:
    assert sha == expect, f"commit_sha is {sha!r}, expected {expect!r} - a stale container is still serving"
print("healthz OK  version", b["version"], " commit", sha, " postgis", b["db"].get("postgis_version"))
'
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$BASE/api/healthz/deep")
[[ "$code" == "200" ]] || { echo "deep healthz returned $code" >&2; exit 1; }
echo "deep healthz OK"
curl -sf --max-time 20 "$BASE/browse" | grep -q 'id="app"' && echo "SPA fallback OK"
# `railway logs` streams by default in CLI 5.26 and would hang a script; --lines
# fetches history and exits. Best-effort only: never fail a good deploy on logs.
if command -v railway >/dev/null 2>&1; then
  echo "→ recent api logs"
  railway logs --service api --environment "$ENV" --lines 20 2>/dev/null || true
fi
