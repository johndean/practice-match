#!/usr/bin/env bash
# Container entrypoint: one image, three roles. Railway sets RAILWAY_SERVICE_NAME;
# a service named worker/*-worker always runs Celery (railway.json's startCommand
# says "api", which would otherwise leave the queue unserved).
# DRY_RUN=1 prints the command that would run instead of exec-ing it, so
# tests/scripts/test_start_sh.sh can exercise role selection without booting
# uvicorn/celery or requiring this repo's dependencies to be installed.
set -euo pipefail

# `${VAR,,}` (bash 4+ lowercasing) isn't available in macOS's stock bash 3.2, so
# lowercase portably with tr — this must run unmodified under both that shell
# and the container's bash (Debian bookworm ships bash 5).
service_name_lc=$(printf '%s' "${RAILWAY_SERVICE_NAME:-}" | tr '[:upper:]' '[:lower:]')

if [[ -n "${RAILWAY_SERVICE_NAME:-}" ]] && [[ "$service_name_lc" =~ ^(worker|celery|.*-worker)$ ]]; then
  role="worker"
elif [[ -n "${1:-}" ]]; then
  role="$1"
elif [[ -n "${RAILWAY_SERVICE_NAME:-}" ]]; then
  case "$service_name_lc" in *migrate*) role="migrate" ;; *) role="api" ;; esac
else
  role="api"
fi
echo "[start.sh] role=$role (RAILWAY_SERVICE_NAME=${RAILWAY_SERVICE_NAME:-unset}, \$1=${1:-})" >&2

case "$role" in
  api)
    # Migrations first (Task 11g): the container proves the schema before it serves, because
    # Railway's pre-deploy hook has not been observed running. Exit 3 = database unreachable:
    # retry, then serve anyway so the static site stays up (sign-ups fail closed with 503 and
    # the next restart applies the files). Any other failure is a broken migration file: stop
    # here, before uvicorn.
    cmd=(uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*')
    if [[ "${DRY_RUN:-0}" == "1" ]]; then echo "python scripts/migrate.py"; echo "${cmd[*]}"; exit 0; fi
    attempt=0
    until python scripts/migrate.py; do
      code=$?
      if [[ "$code" -ne 3 ]]; then echo "[start.sh] migration failed (exit $code) — not serving" >&2; exit "$code"; fi
      attempt=$((attempt + 1))
      if [[ "$attempt" -ge "${MIGRATE_RETRIES:-5}" ]]; then
        echo "[start.sh] database unreachable after $attempt attempts — serving without migrations; sign-ups fail closed until the next restart" >&2
        break
      fi
      sleep "${MIGRATE_RETRY_SLEEP:-5}"
    done
    exec "${cmd[@]}"
    ;;
  worker)
    wcmd=(celery -A app.tasks.celery_app:celery_app worker -B --loglevel=info --concurrency="${CELERY_CONCURRENCY:-2}" --queues=celery)
    if [[ "${DRY_RUN:-0}" == "1" ]]; then
      echo "${wcmd[*]}"
      exit 0
    fi
    # Celery serves no HTTP; Railway's healthcheck would restart-loop the service.
    # Run Celery in the background and a stdlib health server in the foreground;
    # if Celery dies, terminate PID 1 so Railway restarts a clean container.
    "${wcmd[@]}" &
    CELERY_PID=$!
    echo "[start.sh] celery pid=$CELERY_PID" >&2
    (
      while kill -0 "$CELERY_PID" 2>/dev/null; do sleep 2; done
      echo "[start.sh] celery exited — terminating health server" >&2
      kill -TERM 1 2>/dev/null || true
    ) &
    exec python -c "
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
        self.wfile.write(b'{\"status\":\"ok\",\"role\":\"worker\"}')
    def do_HEAD(self):
        self.send_response(200); self.end_headers()
    def log_message(self, *a, **kw): pass
port = int(os.environ.get('PORT', '8000'))
print(f'[worker-health] listening on :{port}', flush=True)
HTTPServer(('0.0.0.0', port), H).serve_forever()
"
    ;;
  migrate)
    mcmd=(python scripts/migrate.py)
    if [[ "${DRY_RUN:-0}" == "1" ]]; then echo "${mcmd[*]}"; else exec "${mcmd[@]}"; fi
    ;;
  *)
    echo "unknown role: $role (expected api | worker | migrate)" >&2; exit 2 ;;
esac
