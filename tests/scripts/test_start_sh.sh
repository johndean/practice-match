#!/usr/bin/env bash
set -euo pipefail; cd "$(dirname "$0")/../.."
fail() { echo "FAIL: $*"; exit 1; }
out=$(DRY_RUN=1 bash scripts/start.sh api) || fail "api role exited non-zero"
first=$(printf '%s\n' "$out" | sed -n 1p); second=$(printf '%s\n' "$out" | sed -n 2p)
[[ "$first" == *"python scripts/migrate.py"* ]] || fail "api role must run the migrations before serving, got first line: $first"
[[ "$second" == *uvicorn* && "$second" == *app.main:app* ]] || fail "api role should then start uvicorn app.main:app, got: $second"
out=$(DRY_RUN=1 RAILWAY_SERVICE_NAME=worker bash scripts/start.sh) || fail "worker role via RAILWAY_SERVICE_NAME exited non-zero"
[[ "$out" != *migrate.py* ]] || fail "the worker must not run migrations (the api does, under the advisory lock)"
if DRY_RUN=1 bash scripts/start.sh bogus 2>/dev/null; then fail "unknown role must exit non-zero"; fi
echo "start.sh dispatcher OK"
