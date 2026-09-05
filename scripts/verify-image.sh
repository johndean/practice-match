#!/usr/bin/env bash
# Builds the image and runs both roles against the local compose services.
set -euo pipefail
cd "$(dirname "$0")/.."
cleanup() { docker rm -f pm-api pm-worker >/dev/null 2>&1 || true; }
trap cleanup EXIT
# Idempotent: a pm-api/pm-worker left behind by an aborted previous run would
# otherwise make the `docker run --name` below fail, so clear them first —
# before even the build, so this is the very first docker call this script makes.
cleanup
docker build --build-arg ENVIRONMENT=test -t practice-match:local .
COMMON=(-e PORT=8000 -e ENVIRONMENT=test -e API_SECRET_KEY=local_only
        -e DATABASE_URL=postgresql://pm:pm_dev_pw@host.docker.internal:5433/practice_match
        -e REDIS_URL=redis://host.docker.internal:6380/0)
docker run -d --name pm-api "${COMMON[@]}" -p 8010:8000 practice-match:local api >/dev/null
docker run -d --name pm-worker "${COMMON[@]}" -e RAILWAY_SERVICE_NAME=worker -p 8011:8000 practice-match:local >/dev/null
sleep 6
api=$(curl -sf http://localhost:8010/api/healthz)
echo "$api" | python3 -c 'import sys,json; b=json.load(sys.stdin); assert b["status"]=="ok" and b["environment"]=="test", b; assert b["db"]["ok"] and b["redis"]["ok"], b; print("api healthz OK", b["db"]["postgis_version"])'
# Below: capture output into a variable before matching rather than piping into
# `grep -q`, which can exit (successfully) before its upstream finishes writing
# and SIGPIPE it — under `set -o pipefail` that poisons the exit status even
# though the match itself succeeded.
index_body=$(curl -sf http://localhost:8010/)
[[ "$index_body" == *'id="app"'* ]] && echo "index.html served"
browse_body=$(curl -sf http://localhost:8010/browse)
[[ "$browse_body" == *'id="app"'* ]] && echo "SPA fallback OK"
# curl -f also exits nonzero on a 404 body, which would independently poison a
# piped pipefail check even when the code itself is an accepted one (200/404).
app_code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8010/_app/)
[[ "$app_code" =~ ^(200|404)$ ]] || { echo "FAIL: /_app/ returned $app_code, expected 200 or 404"; exit 1; }
worker_body=$(curl -sf http://localhost:8011/api/healthz)
[[ "$worker_body" == *'"role":"worker"'* ]] && echo "worker health OK"
worker_logs=$(docker logs pm-worker 2>&1)
[[ "$worker_logs" == *'celery@'* ]] && echo "celery booted"
api_uid=$(docker exec pm-api id -u)
worker_uid=$(docker exec pm-worker id -u)
[[ "$api_uid" == "10001" && "$worker_uid" == "10001" ]] || {
  echo "FAIL: expected uid 10001 in both containers, got api=$api_uid worker=$worker_uid"; exit 1;
}
echo "non-root OK"
