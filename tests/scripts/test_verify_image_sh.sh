#!/usr/bin/env bash
# Exercises scripts/verify-image.sh's control flow (cleanup ordering, the six
# OK-line checks) against fake `docker` and `curl` executables, so it never
# touches the real Docker daemon or the compose services.
set -euo pipefail; cd "$(dirname "$0")/../.."
fail() { echo "FAIL: $*"; exit 1; }

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT
export FAKE_LOG="$WORKDIR/log"
: > "$FAKE_LOG"

FAKE_BIN="$WORKDIR/bin"
mkdir -p "$FAKE_BIN"

cat > "$FAKE_BIN/docker" <<'DOCKEREOF'
#!/usr/bin/env bash
echo "docker $*" >> "$FAKE_LOG"
case "$1" in
  build) exit 0 ;;
  run) echo fake0000container ;;
  rm) exit 0 ;;
  exec) echo 10001 ;;                      # docker exec <name> id -u
  logs) echo "fake celery@fakehost ready." ;;
  *) exit 0 ;;
esac
DOCKEREOF
chmod +x "$FAKE_BIN/docker"

cat > "$FAKE_BIN/curl" <<'CURLEOF'
#!/usr/bin/env bash
echo "curl $*" >> "$FAKE_LOG"
args="$*"
if [[ "$args" == *"-w"* ]]; then
  printf '200'                             # the /_app/ -o /dev/null -w '%{http_code}' probe
elif [[ "$args" == *":8011/api/healthz"* ]]; then
  echo '{"status":"ok","role":"worker"}'
elif [[ "$args" == *"/api/healthz"* ]]; then
  echo '{"status":"ok","environment":"test","db":{"ok":true,"postgis_version":"3.5 fake"},"redis":{"ok":true}}'
else
  echo '<!doctype html><div id="app"></div>'
fi
CURLEOF
chmod +x "$FAKE_BIN/curl"

set +e
PATH="$FAKE_BIN:$PATH" bash scripts/verify-image.sh > "$WORKDIR/out" 2>&1
code=$?
set -e

[[ $code -eq 0 ]] || { cat "$WORKDIR/out"; fail "verify-image.sh exited $code against the fake docker/curl"; }

out=$(cat "$WORKDIR/out")
for line in "api healthz OK" "index.html served" "SPA fallback OK" "worker health OK" "celery booted" "non-root OK"; do
  [[ "$out" == *"$line"* ]] || fail "missing expected output line: $line — got:
$out"
done

first_docker=$(grep '^docker ' "$FAKE_LOG" | head -1)
[[ "$first_docker" == "docker rm -f pm-api pm-worker" ]] || fail "first docker call must be the idempotent cleanup (rm -f pm-api pm-worker), got: $first_docker"

build_line=$(grep '^docker build ' "$FAKE_LOG" | head -1)
[[ "$build_line" == *"--build-arg ENVIRONMENT=qa"* ]] || fail "docker build must receive --build-arg ENVIRONMENT=qa (no default now baked into the Dockerfile), got: $build_line"

echo "verify-image.sh dispatcher OK (stubbed docker/curl)"
