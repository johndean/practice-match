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
    # Migrations run here as well as in railway.json's pre-deploy hook: a QA probe
    # (2026-09-06) found no schema_migrations table after several deploys and the CLI
    # cannot show the hook's output, so the container proves the schema itself before
    # it serves. scripts/migrate.py is idempotent and advisory-locked, so api restarts
    # cannot collide; a failing file exits here (set -e) and uvicorn never starts.
    mcmd=(python scripts/migrate.py)
    cmd=(uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*')
    if [[ "${DRY_RUN:-0}" == "1" ]]; then echo "${mcmd[*]}"; echo "${cmd[*]}"; else "${mcmd[@]}"; exec "${cmd[@]}"; fi
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
