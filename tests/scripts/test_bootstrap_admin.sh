#!/usr/bin/env bash
# The two admin CLIs' shell-facing contract (Task I5): the guards that must hold BEFORE either
# script opens a database connection — a missing --email, and running against production.
#
# Deliberately hermetic: DATABASE_URL points at a port nothing listens on, so any run that reaches
# psycopg2 fails loudly instead of quietly writing an admin grant into whatever database happened
# to be configured. That is also part of the assertion — each refusal below exits on its guard,
# not on a connection error.
set -euo pipefail
cd "$(dirname "$0")/../.."

PY=$(poetry run python -c 'import sys; print(sys.executable)' 2>/dev/null | tail -1)
[[ -n "$PY" ]] || { echo "FAIL: no poetry python"; exit 1; }

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
export DATABASE_URL="postgresql://nobody:nobody@127.0.0.1:1/nothing"
export REDIS_URL="redis://127.0.0.1:1/0"
export API_SECRET_KEY="shell_test_only"
export LINK_BASE_URL="https://qa.foundation.vin"

run() {   # run <script> <environment> [args...] -> sets RC / OUT / ERR
  local script=$1 env=$2; shift 2
  set +e
  ENVIRONMENT="$env" "$PY" "scripts/$script" "$@" >"$tmp/out" 2>"$tmp/err"
  RC=$?
  set -e
  OUT=$(cat "$tmp/out"); ERR=$(cat "$tmp/err")
}

refute_touched_the_database() {
  if grep -qiE "operationalerror|could not connect|connection refused" <<<"$ERR"; then
    echo "FAIL: $1 reached the database before refusing; got: $ERR"; exit 1
  fi
}

# 1. bootstrap_admin refuses without --email (argparse, before anything else happens).
run bootstrap_admin.py qa
[[ $RC -ne 0 ]] || { echo "FAIL: bootstrap_admin.py ran without --email"; exit 1; }
grep -q -- "--email" <<<"$ERR" || { echo "FAIL: no usage message naming --email; got: $ERR"; exit 1; }
refute_touched_the_database "bootstrap_admin.py (no --email)"

# 2. bootstrap_admin refuses on production unless the operator says so explicitly.
run bootstrap_admin.py production --email nobody@example.org
[[ $RC -eq 2 ]] || { echo "FAIL: expected exit 2 on production, got $RC ($ERR)"; exit 1; }
grep -qi "production" <<<"$ERR" || { echo "FAIL: production refusal does not say why; got: $ERR"; exit 1; }
refute_touched_the_database "bootstrap_admin.py (production)"
[[ -z "$OUT" ]] || { echo "FAIL: printed an invite link while refusing; got: $OUT"; exit 1; }

# 3. seed_persona refuses on production outright — there is no override flag.
run seed_persona.py production
[[ $RC -eq 2 ]] || { echo "FAIL: expected exit 2 from seed_persona.py on production, got $RC ($ERR)"; exit 1; }
grep -qi "production" <<<"$ERR" || { echo "FAIL: seed_persona refusal does not say why; got: $ERR"; exit 1; }
refute_touched_the_database "seed_persona.py (production)"
[[ -z "$OUT" ]] || { echo "FAIL: seed_persona.py printed on stdout while refusing; got: $OUT"; exit 1; }

# 4. Neither script prints a password: nothing about a password or a token is ever logged.
for script in bootstrap_admin.py seed_persona.py; do
  if grep -nE 'print\(.*(password|PERSONA_PASSWORD)' "scripts/$script"; then
    echo "FAIL: scripts/$script prints a password"; exit 1
  fi
done

echo "admin CLI guards OK"
