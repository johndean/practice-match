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

# A clean scratch checkout stands in for SOURCE_DIR, so the guard cases below test the
# guard and nothing else: deploy.sh now refuses a SOURCE_DIR with uncommitted changes to
# tracked files (exit 66, tests/scripts/test_deploy_archive.sh), which this repository's
# own working tree may legitimately have while someone is working in it.
src="$tmp/src"; mkdir -p "$src"
git -c init.defaultBranch=main -C "$src" init -q
printf '[project]\nname = "practice-match"\nversion = "0.0.0"\n' > "$src/pyproject.toml"
git -C "$src" add pyproject.toml
git -c commit.gpgsign=false -c user.name=pm-test -c user.email=pm-test@example.invalid -C "$src" commit -q -m scratch

if FAKE_PROJECT="Purchase Order" PATH="$tmp:$PATH" scripts/deploy.sh QA "$src" 2>/dev/null; then echo "FAIL: accepted wrong project"; exit 1; fi
grep -q "UP" "$FAKE_LOG" && { echo "FAIL: railway up ran despite the guard"; exit 1; }
if FAKE_PROJECT="Practice Match" PATH="$tmp:$PATH" scripts/deploy.sh staging 2>/dev/null; then echo "FAIL: accepted unknown environment"; exit 1; fi
FAKE_PROJECT="Practice Match" SKIP_VERIFY=1 PATH="$tmp:$PATH" scripts/deploy.sh QA "$src" >/dev/null
[[ $(grep -c "^UP" "$FAKE_LOG") -eq 2 ]] || { echo "FAIL: expected 2 railway up calls"; cat "$FAKE_LOG"; exit 1; }
grep -q -- "--environment QA --service api" "$FAKE_LOG" || { echo "FAIL: api not deployed to QA"; exit 1; }
grep -q -- "--environment QA --service worker" "$FAKE_LOG" || { echo "FAIL: worker not deployed to QA"; exit 1; }
echo "deploy guard OK"
