#!/usr/bin/env bash
# Post-deploy probes. Usage: verify-deploy.sh QA|production [BASE_URL]
# BASE_URL defaults to the environment's custom domain; pass the *.up.railway.app
# URL (or set VERIFY_BASE_URL) before DNS is live.
#
# EXPECT_SHA defaults to this checkout's HEAD: the point of the probe is to prove
# the code now serving traffic is the code we just deployed, so a stale container
# that answers 200 with an older commit_sha must fail the deploy.
#
# This script is the ONLY gate between a green `railway up` and a broken
# deployment — /api/healthz is deliberately always-200, so Railway's own
# healthcheck passes even with a dead database. Every probe below must therefore
# be able to fail the script; see tests/scripts/test_verify_deploy.sh, whose
# negative cases exist to keep it that way.
set -euo pipefail
ENV="${1:?usage: verify-deploy.sh QA|production [BASE_URL]}"
case "$ENV" in
  QA)         DEFAULT_BASE="https://qa.foundation.vin"; WANT=qa ;;
  production) DEFAULT_BASE="https://foundation.vin";    WANT=production ;;
  *) echo "usage: verify-deploy.sh QA|production [BASE_URL]" >&2; exit 64 ;;
esac
# An explicit target (positional arg or VERIFY_BASE_URL) means an ad hoc probe --
# a *.up.railway.app host before DNS, or a local server in the tests. Only the
# default target is known to correspond to the linked Railway project, so only it
# earns the trailing log tail.
if [[ -n "${2:-}" ]]; then
  BASE="$2"; EXPLICIT_TARGET=1
elif [[ -n "${VERIFY_BASE_URL:-}" ]]; then
  BASE="$VERIFY_BASE_URL"; EXPLICIT_TARGET=1
else
  BASE="$DEFAULT_BASE"; EXPLICIT_TARGET=0
fi
BASE="${BASE%/}"
EXPECT_SHA="${EXPECT_SHA:-$(git rev-parse --short HEAD 2>/dev/null || true)}"

echo "→ GET $BASE/api/healthz"
# Captured once and reused for the mode decision below (fix round 1). -f fails the
# assignment (and, under set -e, the script) on a 4xx/5xx instead of handing python
# an empty body. -sS: no progress meter, but real errors still reach stderr.
health=$(curl -fsS --max-time 20 "$BASE/api/healthz")
printf '%s' "$health" | WANT="$WANT" EXPECT_SHA="$EXPECT_SHA" python3 -c '
import os, sys, json
b = json.load(sys.stdin)
want, expect = os.environ["WANT"], os.environ["EXPECT_SHA"]

def fail(msg):  # one clean line on stderr, exit 1 - no traceback (fix round 1)
    sys.exit(f"FAIL: {msg}")

got = b["environment"]
if got != want:
    fail(f"environment is {got!r}, expected {want!r}: {b}")
db = b["db"]
if not (db["ok"] and b["redis"]["ok"]):
    fail(f"db or redis not ok: {b}")
# A healthy db block without postgis_version means SELECT postgis_version() never
# ran - the extension or the pinned PostGIS image is not what we think it is.
pg = db.get("postgis_version")
if not pg:
    fail(f"postgis_version missing from a healthy db block: {b}")
mode = b.get("site_mode")
if not mode:
    fail(f"site_mode missing from healthz: {b}")
sha = b["commit_sha"]
if expect and sha != expect:
    fail(f"commit_sha is {sha!r}, expected {expect!r} - a stale container is still serving")
print("healthz OK  version", b["version"], " commit", sha, " postgis", pg, " site_mode", mode)
'
code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$BASE/api/healthz/deep")
[[ "$code" == "200" ]] || { echo "FAIL: deep healthz returned $code at $BASE/api/healthz/deep" >&2; exit 1; }
echo "deep healthz OK"
# Which shell to probe depends on SITE_MODE: production runs the coming-soon page
# (probed by its title, the ABSENCE of the marketplace shell, and the /api/interest
# contract), QA and app mode run the marketplace SPA (probed by its #app shell on the
# SPA-fallback route). Bodies are captured, then matched: `cmd | grep -q … && echo OK`
# cannot fail this script under set -e (fix round 1 of Task 8), and a grep -q that
# exits early can SIGPIPE its producer under pipefail.
mode=$(printf '%s' "$health" | python3 -c 'import sys, json; print(json.load(sys.stdin)["site_mode"])')
if [[ "$mode" == "coming_soon" ]]; then
  for path in / /browse; do
    body=$(curl -fsS --max-time 20 "$BASE$path")
    [[ "$body" == *'<title>VIN Foundation — Coming Soon</title>'* ]] \
      || { echo "FAIL: coming-soon shell missing at $BASE$path" >&2; exit 1; }
    # Both shells mount on #app, so the marketplace is recognised by what only it
    # carries: its title and its UI-kit stylesheet (frontend/index.html).
    if [[ "$body" == *'<title>Practice Match'* || "$body" == *'/ds/ui_kits/vin/kit.css'* ]]; then
      echo "FAIL: marketplace shell served in coming-soon mode at $BASE$path" >&2; exit 1
    fi
  done
  echo "coming-soon shell OK"
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 -X POST -H 'Content-Type: application/json' -d '{"email":"not-an-email"}' "$BASE/api/interest")
  [[ "$code" == "422" ]] || { echo "FAIL: interest endpoint answered $code to an invalid address (expected 422)" >&2; exit 1; }
  echo "interest endpoint OK"
else
  body=$(curl -fsS --max-time 20 "$BASE/browse")
  [[ "$body" == *'id="app"'* ]] || { echo "FAIL: SPA fallback missing at $BASE/browse" >&2; exit 1; }
  echo "SPA fallback OK"
fi
# `railway logs` streams by default in CLI 5.26 and would hang a script; --lines
# fetches history and exits. Best-effort only: never fail a good deploy on logs --
# and never invoked for an explicit target or a logged-out CLI, so the shell tests
# stay hermetic and CI does not print a Railway auth error (fix round 2).
if [[ "$EXPLICIT_TARGET" == 1 ]]; then
  echo "logs: skipped (explicit target)"
elif ! command -v railway >/dev/null 2>&1 || ! railway whoami >/dev/null 2>&1; then
  echo "logs: skipped (railway not logged in)"
else
  echo "→ recent api logs"
  railway logs --service api --environment "$ENV" --lines 20 2>/dev/null || true
fi
