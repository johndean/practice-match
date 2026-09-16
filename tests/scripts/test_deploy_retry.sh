#!/usr/bin/env bash
# scripts/deploy-retry.sh retries the ONE failure this project actually sees -- the upload
# timing out -- and never retries a refusal. Measured 2026-09-16: six deploys failed in a day
# at "Uploading... operation timed out", because the committed archive is ~22 MB and this
# machine's upstream measured 15-47 KB/s. Retrying that is right. Retrying a dirty tree or a
# bad argument just repeats a mistake more slowly, which is what these cases pin.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
fail() { echo "FAIL: $*" >&2; exit 1; }

[[ -x scripts/deploy-retry.sh ]] || fail "scripts/deploy-retry.sh missing or not executable"
bash -n scripts/deploy-retry.sh || fail "scripts/deploy-retry.sh does not parse"

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT

# A fake deploy.sh stands in for the real one: it records every call and answers with the
# exit code the case is about. The wrapper must never reach the network to be tested.
mk_fake() {  # mk_fake <exit-code-sequence...>
  mkdir -p "$tmp/bin" "$tmp/repo/scripts"
  printf '%s\n' "$@" > "$tmp/codes"
  cat > "$tmp/repo/scripts/deploy.sh" <<'FAKE'
#!/usr/bin/env bash
echo "CALL $*" >> "$FAKE_LOG"
n=$(wc -l < "$FAKE_LOG" | tr -d ' ')
code=$(sed -n "${n}p" "$FAKE_CODES")
exit "${code:-0}"
FAKE
  chmod +x "$tmp/repo/scripts/deploy.sh"
  cp scripts/deploy-retry.sh "$tmp/repo/scripts/deploy-retry.sh"
  : > "$tmp/log"
}

# --- 1. a bad argument is refused before anything is called --------------------
mk_fake 0
FAKE_LOG="$tmp/log" FAKE_CODES="$tmp/codes" "$tmp/repo/scripts/deploy-retry.sh" nonsense >/dev/null 2>&1 \
  && fail "an unknown environment must not exit 0"
code=$?; [[ $code -eq 64 ]] || fail "an unknown environment must exit 64, got $code"
[[ ! -s "$tmp/log" ]] || fail "nothing may be called for a bad argument; got: $(cat "$tmp/log")"

# --- 2. a transient failure IS retried, and success ends it --------------------
mk_fake 67 67 0
set +e
FAKE_LOG="$tmp/log" FAKE_CODES="$tmp/codes" ATTEMPTS=3 DEPLOY_RETRY_SLEEP=0 \
  "$tmp/repo/scripts/deploy-retry.sh" QA "$tmp/repo" >/dev/null 2>&1
code=$?
set -e
[[ $code -eq 0 ]] || fail "a deploy that succeeds on the third attempt must exit 0, got $code"
[[ $(grep -c '^CALL ' "$tmp/log") -eq 3 ]] || fail "expected 3 attempts, got: $(cat "$tmp/log")"

# --- 3. a REFUSAL is never retried -------------------------------------------
# 64-66 are deploy.sh's own refusals: bad argument, dirty tree, unreadable version. Retrying
# one wastes a twenty-minute upload window on a mistake that will not fix itself.
for refusal in 64 65 66; do
  mk_fake "$refusal" 0 0
  set +e
  FAKE_LOG="$tmp/log" FAKE_CODES="$tmp/codes" ATTEMPTS=3 DEPLOY_RETRY_SLEEP=0 \
    "$tmp/repo/scripts/deploy-retry.sh" QA "$tmp/repo" >/dev/null 2>&1
  code=$?
  set -e
  [[ $code -eq $refusal ]] || fail "exit $refusal must pass straight through, got $code"
  [[ $(grep -c '^CALL ' "$tmp/log") -eq 1 ]] || fail "exit $refusal must not be retried; calls: $(cat "$tmp/log")"
done

# --- 4. the environment and SOURCE_DIR reach deploy.sh unchanged ---------------
mk_fake 0
FAKE_LOG="$tmp/log" FAKE_CODES="$tmp/codes" "$tmp/repo/scripts/deploy-retry.sh" production "$tmp/repo" >/dev/null 2>&1
grep -q "^CALL production $tmp/repo$" "$tmp/log" \
  || fail "the environment and SOURCE_DIR must reach deploy.sh verbatim; got: $(cat "$tmp/log")"

echo "deploy retry OK"
