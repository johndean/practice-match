#!/usr/bin/env bash
# Deploy to one Railway environment. Guards John's standing rule: read `railway status`
# back and refuse unless the linked project is Practice Match — this machine runs
# several Railway projects and `railway up` ships to whatever is linked.
#
# The guard is not theoretical: ~/.railway/config.json links $HOME itself, and the
# CLI resolves a project by walking up the tree, so an unlinked directory anywhere
# under /Users/johndean inherits that project. Without this check `railway up` from
# a fresh clone would deploy this repo over an unrelated production service.
set -euo pipefail
ENV="${1:-}"
[[ "$ENV" == "QA" || "$ENV" == "production" ]] || { echo "usage: $0 QA|production" >&2; exit 64; }
cd "$(dirname "$0")/.."
PROJECT=$(railway status --json | python3 -c 'import sys,json; print(json.load(sys.stdin).get("name",""))')
if [[ "$PROJECT" != "Practice Match" ]]; then
  echo "🚦 STOP: railway is linked to '${PROJECT:-nothing}', not 'Practice Match'. Fix with: railway link" >&2
  exit 65
fi
echo "🚦 railway status → Project: $PROJECT | target environment: $ENV"
SHA=$(git rev-parse --short HEAD)
for svc in api worker; do
  railway variable set "COMMIT_SHA=$SHA" --service "$svc" --environment "$ENV" --skip-deploys >/dev/null
  echo "→ railway up --environment $ENV --service $svc --ci  (commit $SHA)"
  railway up --environment "$ENV" --service "$svc" --ci
done
[[ -n "${SKIP_VERIFY:-}" ]] || scripts/verify-deploy.sh "$ENV"
