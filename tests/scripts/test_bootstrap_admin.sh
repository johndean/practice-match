#!/usr/bin/env bash
# The seed/admin CLIs' shell-facing contract (Task I5; scripts/seed_listings.py joined in L4
# round 1b): the guards that must hold BEFORE any of these scripts opens a database connection —
# a missing --email, and running against production.
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

# 4. seed_listings refuses on production unless the operator says so out loud (L4 round 1b).
#    Same shape as bootstrap_admin's --production, and D7's "never on production without John's
#    go" is what it enforces: these are demo hospitals, not the stakeholders' listings.
run seed_listings.py production
[[ $RC -eq 2 ]] || { echo "FAIL: expected exit 2 from seed_listings.py on production, got $RC ($ERR)"; exit 1; }
grep -qi "production" <<<"$ERR" || { echo "FAIL: seed_listings refusal does not say why; got: $ERR"; exit 1; }
grep -q -- "--production" <<<"$ERR" || { echo "FAIL: the refusal does not name the flag that lifts it; got: $ERR"; exit 1; }
refute_touched_the_database "seed_listings.py (production)"
[[ -z "$OUT" ]] || { echo "FAIL: seed_listings.py printed on stdout while refusing; got: $OUT"; exit 1; }

# 5. ...and WITH the flag it gets past the guard: the only thing that stops it here is the
#    unreachable DSN (exit 3), which is also the proof that the refusal above was the guard and
#    not a connection failure wearing its clothes.
run seed_listings.py production --production
[[ $RC -eq 3 ]] || { echo "FAIL: --production should reach the database and fail on it (exit 3), got $RC ($ERR)"; exit 1; }
grep -qiE "operationalerror|unreachable" <<<"$ERR" || { echo "FAIL: expected a database-unreachable message; got: $ERR"; exit 1; }
grep -qi "production" <<<"$OUT" || { echo "FAIL: a production run must announce itself on its first line of stdout; got: $OUT"; exit 1; }

# 6. None of the three scripts prints a password: nothing about a password or a token is ever logged.
for script in bootstrap_admin.py seed_persona.py seed_listings.py; do
  if grep -nE 'print\(.*(password|PERSONA_PASSWORD)' "scripts/$script"; then
    echo "FAIL: scripts/$script prints a password"; exit 1
  fi
done

echo "admin CLI guards OK"
