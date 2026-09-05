#!/usr/bin/env bash
# deploy.sh must refuse to run `railway up` unless the linked project is Practice Match,
# must reject unknown environments, and must deploy api then worker when the guard passes.
set -euo pipefail
cd "$(dirname "$0")/../.."
[[ -x scripts/deploy.sh ]] || { echo "FAIL: scripts/deploy.sh missing or not executable"; exit 1; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
export FAKE_LOG="$tmp/log"; : > "$FAKE_LOG"
cat > "$tmp/railway" <<'F'
#!/usr/bin/env bash
case "$1" in
  status) echo "{\"name\":\"${FAKE_PROJECT}\"}" ;;
  variable) : ;;
  up) echo "UP $*" >> "$FAKE_LOG" ;;
esac
F
chmod +x "$tmp/railway"

if FAKE_PROJECT="Purchase Order" PATH="$tmp:$PATH" scripts/deploy.sh QA 2>/dev/null; then echo "FAIL: accepted wrong project"; exit 1; fi
grep -q "UP" "$FAKE_LOG" && { echo "FAIL: railway up ran despite the guard"; exit 1; }
if FAKE_PROJECT="Practice Match" PATH="$tmp:$PATH" scripts/deploy.sh staging 2>/dev/null; then echo "FAIL: accepted unknown environment"; exit 1; fi
FAKE_PROJECT="Practice Match" SKIP_VERIFY=1 PATH="$tmp:$PATH" scripts/deploy.sh QA >/dev/null
[[ $(grep -c "^UP" "$FAKE_LOG") -eq 2 ]] || { echo "FAIL: expected 2 railway up calls"; cat "$FAKE_LOG"; exit 1; }
grep -q -- "--environment QA --service api" "$FAKE_LOG" || { echo "FAIL: api not deployed to QA"; exit 1; }
grep -q -- "--environment QA --service worker" "$FAKE_LOG" || { echo "FAIL: worker not deployed to QA"; exit 1; }
echo "deploy guard OK"
