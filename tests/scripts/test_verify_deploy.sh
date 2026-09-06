#!/usr/bin/env bash
# verify-deploy.sh is the only gate between a green `railway up` and a broken
# deployment: /api/healthz is deliberately always-200, so Railway's own healthcheck
# passes even with a dead database. Every probe it makes must therefore be able to
# FAIL the script — the negative cases below are the point of this file, not the
# happy path.
#
# This suite is hermetic: a fake `railway` shadows the real CLI on PATH and records
# every invocation, so the tests never touch the network or a Railway account (fix
# round 2). Local HTTP servers stand in for the deployment.
set -euo pipefail; cd "$(dirname "$0")/../.."
fail() { echo "FAIL: $*"; exit 1; }

tmp=$(mktemp -d)
export FAKE_RAILWAY_LOG="$tmp/railway-calls"
: > "$FAKE_RAILWAY_LOG"
cat > "$tmp/railway" <<'F'
#!/usr/bin/env bash
echo "railway $*" >> "$FAKE_RAILWAY_LOG"
case "$1" in
  whoami) echo "Logged in as fake@example.com" ;;
  logs)   echo "(fake log line)" ;;
esac
F
chmod +x "$tmp/railway"
export PATH="$tmp:$PATH"

SRV=""
PORT=0
stop_server() {
  if [[ -n "$SRV" ]]; then kill "$SRV" 2>/dev/null || true; wait "$SRV" 2>/dev/null || true; SRV=""; fi
}
cleanup() { stop_server; rm -rf "$tmp"; }
trap cleanup EXIT

railway_calls() { wc -l < "$FAKE_RAILWAY_LOG" | tr -d ' '; }

# start_server <mode>. Modes: ok | spa_missing | deep_503 | no_postgis | no_site_mode |
#   coming_ok | coming_wrong_shell | coming_interest_500 | coming_leak | missing_keys | db_null |
#   not_json | deep_json
# Binds port 0 (the OS picks a free ephemeral port) and prints it, once, before serving —
# fixed ports (8765-8768) collided under a concurrent run of this same script (fix round 3,
# re-review observation), and a bind failure in the backgrounded server was otherwise
# invisible: the script never checked that its own server actually came up.
PORTFILE_N=0
start_server() {
  PORTFILE_N=$((PORTFILE_N + 1))
  local portfile="$tmp/port.$PORTFILE_N"
  MODE="$1" python3 - > "$portfile" <<'PY' &
import json, os
from http.server import BaseHTTPRequestHandler, HTTPServer

MODE = os.environ.get("MODE", "ok")
BODY = {"status": "ok", "version": "0.1.0", "environment": "qa", "commit_sha": "abc1234",
        "site_mode": "app",
        "db": {"ok": True, "postgis_version": "3.5.2"}, "redis": {"ok": True}}
if MODE == "no_postgis":
    del BODY["db"]["postgis_version"]
if MODE == "no_site_mode":
    del BODY["site_mode"]
if MODE in ("coming_ok", "coming_wrong_shell", "coming_interest_500", "coming_leak"):
    BODY["site_mode"] = "coming_soon"
if MODE == "missing_keys":
    BODY = {"status": "ok"}  # malformed: every other required key absent (fix round 2)
if MODE == "db_null":
    BODY["db"] = None  # malformed: key present but not an object (fix round 3)

SHELL_OK = b'<!doctype html><div id="app"></div>'
SHELL_BAD = b'<!doctype html><p>404 - no app shell here</p>'
COMING_SHELL = "<!doctype html><title>VIN Foundation — Coming Soon</title>".encode("utf-8")
# Carries the coming-soon title AND a marketplace-only marker (its UI-kit stylesheet,
# frontend/index.html) plus the shared #app mount point both shells use — a leaked
# marketplace bundle behind a patched <title> (FR1 C1).
LEAK_SHELL = (
    "<!doctype html><title>VIN Foundation — Coming Soon</title>"
    '<link rel="stylesheet" href="/ds/ui_kits/vin/kit.css"><div id="app"></div>'
).encode("utf-8")

class H(BaseHTTPRequestHandler):
    def _send(self, code, ctype, payload):
        self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers()
        self.wfile.write(payload)
    def do_GET(self):
        if self.path.startswith("/api/healthz/deep"):
            self._send(503 if MODE == "deep_503" else 200, "application/json", json.dumps(BODY).encode())
        elif self.path.startswith("/api/healthz"):
            if MODE == "not_json":
                # A 200 that curl -f does not block, but whose body a proxy's HTML
                # error page replaced instead of the real JSON (fix round 4).
                self._send(200, "text/html", b"<html>upstream error</html>")
            elif MODE == "deep_json":
                # Valid JSON syntax, but nested deep enough to blow Python's json
                # module's recursion limit (RecursionError, a ValueError sibling
                # that a bare `except ValueError` does not catch - fix round 5).
                self._send(200, "application/json", ("[" * 20000 + "]" * 20000).encode())
            else:
                self._send(200, "application/json", json.dumps(BODY).encode())
        elif self.path in ("/", "/browse"):
            if MODE == "coming_wrong_shell":
                self._send(200, "text/html", SHELL_OK)  # marketplace shell, no coming-soon title
            elif MODE == "coming_leak":
                self._send(200, "text/html", LEAK_SHELL)
            elif MODE in ("coming_ok", "coming_interest_500"):
                self._send(200, "text/html", COMING_SHELL)
            else:
                self._send(200, "text/html", SHELL_BAD if MODE == "spa_missing" else SHELL_OK)
        else:
            self._send(404, "text/html", b"not found")
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length:
            self.rfile.read(length)
        if self.path == "/api/interest":
            if MODE == "coming_interest_500":
                self._send(500, "application/json", b'{"error":"server_error"}')
            else:
                self._send(422, "application/json", b'{"error":"invalid_email"}')
        else:
            self._send(404, "text/html", b"not found")
    def log_message(self, *a): pass

srv = HTTPServer(("127.0.0.1", 0), H)   # port 0: OS assigns a free ephemeral port
print(srv.server_port, flush=True)      # announced once, read back by the shell caller
srv.serve_forever()
PY
  SRV=$!
  # Poll (bounded) for the announced port instead of a fixed sleep: a concurrent run can
  # never collide on a bind, but the server's own startup time still varies.
  PORT=""
  for _ in $(seq 1 50); do
    [[ -s "$portfile" ]] && { PORT=$(cat "$portfile"); break; }
    sleep 0.05
  done
  [[ -n "$PORT" ]] || fail "start_server ($1): the background server never announced a port"
}

# --- 1. healthy target verifies, and prints all three OK lines -----------------
start_server ok
: > "$FAKE_RAILWAY_LOG"
out=$(VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh QA) || fail "a healthy target must verify; output: $out"
for line in "healthz OK" "deep healthz OK" "SPA fallback OK"; do [[ "$out" == *"$line"* ]] || fail "missing '$line' in: $out"; done
[[ "$out" == *"3.5.2"* ]] || fail "the postgis version must be printed; got: $out"

# An explicit target is an ad hoc probe: the Railway CLI must not be invoked at all,
# so this suite stays hermetic and CI never sees a Railway auth error.
n=$(railway_calls)
[[ "$n" -eq 0 ]] || fail "explicit target must not invoke the railway CLI; got $n invocation(s): $(cat "$FAKE_RAILWAY_LOG")"
[[ "$out" == *"logs: skipped (explicit target)"* ]] || fail "must say why the log tail was skipped; got: $out"

# --- 2. environment mismatch fails --------------------------------------------
if VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh production >/dev/null 2>&1; then fail "environment mismatch must fail"; fi

# --- 3. commit mismatch fails (a stale container still serving) ----------------
if VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=deadbee bash scripts/verify-deploy.sh QA >/dev/null 2>&1; then fail "commit mismatch must fail"; fi
stop_server

# --- 4. the SPA shell is missing: healthz and deep are healthy, /browse is not --
start_server spa_missing
if out=$(VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh QA 2>&1); then
  fail "a missing SPA shell must fail the script; it exited 0 with: $out"
fi
[[ "$out" == *"SPA fallback missing"* ]] || fail "the SPA failure must name itself; got: $out"
[[ "$out" != *"SPA fallback OK"* ]] || fail "must not claim SPA fallback OK when the shell is missing; got: $out"
stop_server

# --- 5. deep healthz 503 fails, and the message names deep ---------------------
start_server deep_503
if out=$(VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh QA 2>&1); then
  fail "a 503 from /api/healthz/deep must fail the script; it exited 0 with: $out"
fi
[[ "$out" == *"deep"* ]] || fail "the deep-healthz failure must name deep; got: $out"
[[ "$out" == *"503"* ]] || fail "the deep-healthz failure should report the status code; got: $out"
stop_server

# --- 6. db.ok true but postgis_version absent: the pin/extension is not proven --
start_server no_postgis
if out=$(VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh QA 2>&1); then
  fail "a missing postgis_version must fail the script; it exited 0 with: $out"
fi
[[ "$out" == *"postgis_version missing"* ]] || fail "the missing-postgis failure must name itself; got: $out"
stop_server

# --- 7. coming-soon mode: shell present at / and /browse, interest 422s --------
start_server coming_ok
out=$(VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh QA 2>&1) || fail "coming-soon mode must verify; output: $out"
for line in "site_mode coming_soon" "coming-soon shell OK" "interest endpoint OK"; do [[ "$out" == *"$line"* ]] || fail "missing '$line' in: $out"; done
stop_server

# --- 8. coming-soon mode but the marketplace shell is served, not the title -----
start_server coming_wrong_shell
if out=$(VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh QA 2>&1); then
  fail "the wrong shell in coming-soon mode must fail the script; it exited 0 with: $out"
fi
[[ "$out" == *"coming-soon shell missing"* ]] || fail "the coming-soon shell failure must name itself; got: $out"
stop_server

# --- 9. coming-soon mode, /api/interest 500s ------------------------------------
start_server coming_interest_500
if out=$(VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh QA 2>&1); then
  fail "an interest-endpoint 500 must fail the script; it exited 0 with: $out"
fi
[[ "$out" == *"interest"* ]] || fail "the interest failure must name itself; got: $out"
stop_server

# --- 10. healthz body without site_mode fails, and the message names it --------
start_server no_site_mode
if out=$(VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh QA 2>&1); then
  fail "a healthz body missing site_mode must fail the script; it exited 0 with: $out"
fi
# fix round 2 folded the site_mode presence check into the generic missing-keys
# check (site_mode is one of the required keys), so an absent site_mode now reports
# via that same clean path rather than its own bespoke message.
[[ "$out" == *"missing keys"* && "$out" == *"site_mode"* ]] || fail "the missing-site_mode failure must name itself; got: $out"
[[ "$out" != *"Traceback"* ]] || fail "the failure must be one clean FAIL line, not a Python traceback; got: $out"
stop_server

# --- 11. coming-soon mode but the marketplace shell leaks through (FR1 C1) ------
# Both shells mount on #app, so a patched <title> alone cannot prove the marketplace
# bundle isn't also being served; the script must also check for absence of the
# marketplace-only markers (its own title, its UI-kit stylesheet).
start_server coming_leak
if out=$(VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh QA 2>&1); then
  fail "a leaked marketplace shell in coming-soon mode must fail the script; it exited 0 with: $out"
fi
[[ "$out" == *"marketplace shell served in coming-soon mode"* ]] || fail "the leak failure must name itself; got: $out"
stop_server

# --- 12. malformed healthz body (required keys absent) fails, no traceback -----
start_server missing_keys
if out=$(VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh QA 2>&1); then
  fail "a malformed healthz body must fail the script; it exited 0 with: $out"
fi
[[ "$out" == *"FAIL: healthz body missing keys"* ]] || fail "the malformed-body failure must name itself; got: $out"
[[ "$out" != *"Traceback"* ]] || fail "the failure must be one clean FAIL line, not a Python traceback; got: $out"
stop_server

# --- 13. db present but not an object (e.g. null) fails, no traceback ----------
start_server db_null
if out=$(VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh QA 2>&1); then
  fail "a null db block must fail the script; it exited 0 with: $out"
fi
[[ "$out" == *"FAIL: healthz db/redis blocks are not objects"* ]] || fail "the non-object db/redis failure must name itself; got: $out"
[[ "$out" != *"Traceback"* ]] || fail "the failure must be one clean FAIL line, not a Python traceback; got: $out"
stop_server

# --- 14. a 200 healthz response whose body isn't JSON fails, no traceback ------
# curl -f only blocks on 4xx/5xx; a proxy that swaps in an HTML error page on a 200
# must still be caught by the parse itself, not just by the checks after it.
start_server not_json
if out=$(VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh QA 2>&1); then
  fail "a non-JSON healthz body must fail the script; it exited 0 with: $out"
fi
[[ "$out" == *"FAIL: healthz body is not JSON"* ]] || fail "the non-JSON failure must name itself; got: $out"
[[ "$out" != *"Traceback"* ]] || fail "the failure must be one clean FAIL line, not a Python traceback; got: $out"
stop_server

# --- 15. a deeply-nested-but-syntactically-valid healthz body fails, no traceback -
# `except ValueError` around json.load does not catch RecursionError (round cap).
start_server deep_json
if out=$(VERIFY_BASE_URL="http://127.0.0.1:$PORT" EXPECT_SHA=abc1234 bash scripts/verify-deploy.sh QA 2>&1); then
  fail "a deeply-nested healthz body must fail the script; it exited 0 with: $out"
fi
[[ "$out" == *"FAIL: healthz body is not JSON"* ]] || fail "the deeply-nested-body failure must name itself; got: $out"
[[ "$out" != *"Traceback"* ]] || fail "the failure must be one clean FAIL line, not a Python traceback; got: $out"
stop_server

# --- no case anywhere in this suite may reach the Railway CLI ------------------
n=$(railway_calls)
[[ "$n" -eq 0 ]] || fail "the suite must be hermetic; railway was invoked $n time(s): $(cat "$FAKE_RAILWAY_LOG")"

echo "verify-deploy.sh OK"
