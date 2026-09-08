#!/usr/bin/env bash
# Exercises scripts/verify-image.sh's control flow (cleanup ordering, the eight
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

# A function, not a bare heredoc: the I8 case at the end of this file needs the HEALTHY curl
# back after the O1 case has replaced it with a broken one, and a second copy of the body would
# be a second thing to keep in step.
write_healthy_curl() {
cat > "$FAKE_BIN/curl" <<'CURLEOF'
#!/usr/bin/env bash
echo "curl $*" >> "$FAKE_LOG"
args="$*"
if [[ "$args" == *"-w"* ]]; then
  printf '200'                             # the /_app/ -o /dev/null -w '%{http_code}' probe
elif [[ "$args" == *":8011/api/healthz"* ]]; then
  echo '{"status":"ok","role":"worker"}'
elif [[ "$args" == *":8012/api/healthz"* ]]; then
  echo '{"status":"ok","site_mode":"coming_soon"}'
elif [[ "$args" == *":8012/"* ]]; then
  echo '<!doctype html><title>VIN Foundation — Coming Soon</title><div id="app"></div>'
elif [[ "$args" == *"/api/healthz"* ]]; then
  echo '{"status":"ok","environment":"test","db":{"ok":true,"postgis_version":"3.5 fake"},"redis":{"ok":true}}'
else
  echo '<!doctype html><div id="app"></div>'
fi
CURLEOF
chmod +x "$FAKE_BIN/curl"
}
write_healthy_curl

set +e
PATH="$FAKE_BIN:$PATH" bash scripts/verify-image.sh > "$WORKDIR/out" 2>&1
code=$?
set -e

[[ $code -eq 0 ]] || { cat "$WORKDIR/out"; fail "verify-image.sh exited $code against the fake docker/curl"; }

out=$(cat "$WORKDIR/out")
for line in "api healthz OK" "index.html served" "SPA fallback OK" "worker health OK" "celery booted" "non-root OK" "seed data in image OK" "coming soon OK"; do
  [[ "$out" == *"$line"* ]] || fail "missing expected output line: $line — got:
$out"
done

first_docker=$(grep '^docker ' "$FAKE_LOG" | head -1)
[[ "$first_docker" == "docker rm -f pm-api pm-worker pm-coming" ]] || fail "first docker call must be the idempotent cleanup (rm -f pm-api pm-worker pm-coming), got: $first_docker"

build_line=$(grep '^docker build ' "$FAKE_LOG" | head -1)
[[ "$build_line" == *"--build-arg ENVIRONMENT=qa"* ]] || fail "docker build must receive --build-arg ENVIRONMENT=qa (no default now baked into the Dockerfile), got: $build_line"

echo "verify-image.sh dispatcher OK (stubbed docker/curl)"

# --- O1: a broken index.html (no id="app") must fail the script, not silently pass ---
# `[[ … ]] && echo "OK"` is exempt from `set -e`, so a failed match used to print nothing
# and exit 0; a fake curl whose root body lacks the app shell proves the check can now fail.
cat > "$FAKE_BIN/curl" <<'CURLEOF2'
#!/usr/bin/env bash
echo "curl $*" >> "$FAKE_LOG"
args="$*"
if [[ "$args" == *"-w"* ]]; then
  printf '200'
elif [[ "$args" == *":8011/api/healthz"* ]]; then
  echo '{"status":"ok","role":"worker"}'
elif [[ "$args" == *":8012/api/healthz"* ]]; then
  echo '{"status":"ok","site_mode":"coming_soon"}'
elif [[ "$args" == *":8012/"* ]]; then
  echo '<!doctype html><title>VIN Foundation — Coming Soon</title><div id="app"></div>'
elif [[ "$args" == *"/api/healthz"* ]]; then
  echo '{"status":"ok","environment":"test","db":{"ok":true,"postgis_version":"3.5 fake"},"redis":{"ok":true}}'
elif [[ "$args" == *"http://localhost:8010/" ]]; then
  echo '<!doctype html><p>no app shell here</p>'    # broken index.html (O1 negative case)
else
  echo '<!doctype html><div id="app"></div>'
fi
CURLEOF2
chmod +x "$FAKE_BIN/curl"
: > "$FAKE_LOG"

set +e
PATH="$FAKE_BIN:$PATH" bash scripts/verify-image.sh > "$WORKDIR/out2" 2>&1
code2=$?
set -e

[[ $code2 -ne 0 ]] || { cat "$WORKDIR/out2"; fail "verify-image.sh must fail when index.html lacks id=\"app\"; it exited 0"; }
out2=$(cat "$WORKDIR/out2")
[[ "$out2" == *"FAIL: index.html"* ]] || fail "the broken-index failure must name itself; got: $out2"

echo "verify-image.sh negative case OK (O1)"

# --- I8: a seeds/ directory missing from the image must fail the script ---
# The O1 case above left a broken-index curl behind; this case must fail on the seeds check,
# not on that one.
write_healthy_curl
cat > "$FAKE_BIN/docker" <<'DOCKEREOF3'
#!/usr/bin/env bash
echo "docker $*" >> "$FAKE_LOG"
case "$1" in
  build) exit 0 ;;
  run) echo fake0000container ;;
  rm) exit 0 ;;
  exec) if [[ "$*" == *"test -f"* ]]; then exit 1; fi; echo 10001 ;;
  logs) echo "fake celery@fakehost ready." ;;
  *) exit 0 ;;
esac
DOCKEREOF3
chmod +x "$FAKE_BIN/docker"
: > "$FAKE_LOG"

set +e
PATH="$FAKE_BIN:$PATH" bash scripts/verify-image.sh > "$WORKDIR/out3" 2>&1
code3=$?
set -e

[[ $code3 -ne 0 ]] || { cat "$WORKDIR/out3"; fail "verify-image.sh must fail when seeds/ is missing from the image; it exited 0"; }
out3=$(cat "$WORKDIR/out3")
[[ "$out3" == *"FAIL: seeds/hospitals.json missing from the image"* ]] || fail "the missing-seeds failure must name the file; got: $out3"

echo "verify-image.sh seed-data negative case OK (I8)"
