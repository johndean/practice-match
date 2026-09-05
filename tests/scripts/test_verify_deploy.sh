#!/usr/bin/env bash
set -euo pipefail; cd "$(dirname "$0")/../.."
fail() { echo "FAIL: $*"; exit 1; }
PORT=8765
python3 - "$PORT" <<'PY' &
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
BODY = {"status": "ok", "version": "0.1.0", "environment": "qa", "commit_sha": "abc1234", "db": {"ok": True, "postgis_version": "3.5.2"}, "redis": {"ok": True}}
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/healthz"):
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(json.dumps(BODY).encode())
        else:
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(b'<!doctype html><div id="app"></div>')
    def log_message(self, *a): pass
HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
PY
SRV=$!; trap 'kill $SRV' EXIT; sleep 0.5
out=$(VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh QA) || fail "a healthy target must verify; output: $out"
for line in "healthz OK" "deep healthz OK" "SPA fallback OK"; do [[ "$out" == *"$line"* ]] || fail "missing '$line' in: $out"; done
if VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh production >/dev/null 2>&1; then fail "environment mismatch must fail"; fi
if VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=deadbee bash scripts/verify-deploy.sh QA >/dev/null 2>&1; then fail "commit mismatch must fail"; fi
echo "verify-deploy.sh OK"
