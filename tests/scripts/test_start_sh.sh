#!/usr/bin/env bash
set -euo pipefail; cd "$(dirname "$0")/../.."
fail() { echo "FAIL: $*"; exit 1; }
out=$(DRY_RUN=1 bash scripts/start.sh api) || fail "api role exited non-zero"
[[ "$out" == *uvicorn* && "$out" == *app.main:app* ]] || fail "api role should start uvicorn app.main:app, got: $out"
out=$(DRY_RUN=1 RAILWAY_SERVICE_NAME=worker bash scripts/start.sh) || fail "worker role via RAILWAY_SERVICE_NAME exited non-zero"
[[ "$out" == *celery* && "$out" == *worker* ]] || fail "worker role should start a celery worker, got: $out"
if DRY_RUN=1 bash scripts/start.sh bogus 2>/dev/null; then fail "unknown role must exit non-zero"; fi
echo "start.sh dispatcher OK"
