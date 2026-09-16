#!/usr/bin/env bash
set -euo pipefail; cd "$(dirname "$0")/../.."
fail() { echo "FAIL: $*"; exit 1; }
out=$(DRY_RUN=1 bash scripts/start.sh api) || fail "api role exited non-zero"
first=$(printf '%s\n' "$out" | sed -n 1p); second=$(printf '%s\n' "$out" | sed -n 2p)
[[ "$first" == *"python scripts/migrate.py"* ]] || fail "api role must run the migrations before serving, got first line: $first"
[[ "$second" == *uvicorn* && "$second" == *app.main:app* ]] || fail "api role should then start uvicorn app.main:app, got: $second"
out=$(DRY_RUN=1 RAILWAY_SERVICE_NAME=worker bash scripts/start.sh) || fail "worker role via RAILWAY_SERVICE_NAME exited non-zero"
[[ "$out" == *celery* && "$out" == *worker* ]] || fail "worker role should start a celery worker, got: $out"
[[ "$out" != *migrate.py* ]] || fail "the worker must not run migrations (the api does, under the advisory lock)"
# Spec 2026-09-09 E: `media.*` is routed to its own queue so a burst of fifty photographs cannot
# delay the minutely mail drain — but ONE worker process consumes both, so a queue the worker does
# not subscribe to is a queue nothing ever drains. Beat publishes `media.sweep` by name every five
# minutes whatever this line says, so getting it wrong is silent.
[[ "$out" == *"--queues=celery,media"* ]] || fail "the worker must consume both queues, got: $out"
# MEASURED: `import onnxruntime` writes a device id and a SQLite database under $HOME before any
# session exists, so the Python switch `disable_telemetry_events()` cannot prevent it and only an
# environment variable set before the process starts can. The worker is the only role that loads an
# engine.
[[ "$out" == *"ORT_DISABLE_TELEMETRY=1"* ]] || fail "the worker must disable onnxruntime telemetry before it imports an engine, got: $out"

# --- migration outcomes at api boot (fake python + fake uvicorn on PATH; no DRY_RUN) ---
FAKE=$(mktemp -d); trap 'rm -rf "$FAKE"' EXIT
cat > "$FAKE/python" <<'PY'
#!/usr/bin/env bash
# exit with the first code listed in $CODES_FILE, consuming it; 0 when the file is empty
code=$(head -1 "$CODES_FILE"); sed -i.bak 1d "$CODES_FILE"; echo "fake migrate exit ${code:-0}" >&2; exit "${code:-0}"
PY
printf '#!/usr/bin/env bash\necho "fake uvicorn $*"\n' > "$FAKE/uvicorn"; chmod +x "$FAKE/python" "$FAKE/uvicorn"
run_api() { CODES_FILE="$FAKE/codes" PATH="$FAKE:$PATH" MIGRATE_RETRIES=3 MIGRATE_RETRY_SLEEP=0 bash scripts/start.sh api 2>&1; }

printf '3\n3\n' > "$FAKE/codes"; out=$(run_api) || fail "unreachable-then-ok must serve, exited $?"
[[ "$out" == *"fake uvicorn"* ]] || fail "after the database comes back the api must start uvicorn, got: $out"
[[ $(grep -c "fake migrate exit 3" <<<"$out") -eq 2 ]] || fail "expected two retries before success, got: $out"

printf '3\n3\n3\n3\n' > "$FAKE/codes"; out=$(run_api) || fail "persistently unreachable must still serve, exited $?"
[[ "$out" == *"serving without migrations"* && "$out" == *"fake uvicorn"* ]] || fail "after MIGRATE_RETRIES the api must serve and say so, got: $out"

printf '1\n' > "$FAKE/codes"; set +e; out=$(run_api); code=$?; set -e
[[ $code -ne 0 && "$out" != *"fake uvicorn"* && "$out" == *"migration failed"* ]] || fail "a failing migration file must stop the container before uvicorn (exit $code), got: $out"

# Exit 4 = an already-applied migration whose file has changed (scripts/migrate.py's checksum
# ledger, Task I5c Step 0). Like 1 and unlike 3 it is NOT retryable: the tree disagrees with the
# database, and retrying cannot make it agree — stop, and do not serve.
printf '4\n' > "$FAKE/codes"; set +e; out=$(run_api); code=$?; set -e
[[ $code -eq 4 && "$out" != *"fake uvicorn"* && "$out" == *"migration failed (exit 4)"* ]] || fail "a changed applied migration (exit 4) must stop the container before uvicorn (exit $code), got: $out"

out=$(DRY_RUN=1 bash scripts/start.sh seed) || fail "seed role exited non-zero"
[[ "$out" == *"python scripts/seed_listings.py"* ]] || fail "seed role should run the seeder, got: $out"
[[ "$out" != *uvicorn* && "$out" != *celery* ]] || fail "the seed role must not start a server, got: $out"

if DRY_RUN=1 bash scripts/start.sh bogus 2>/dev/null; then fail "unknown role must exit non-zero"; fi
echo "start.sh dispatcher OK"
