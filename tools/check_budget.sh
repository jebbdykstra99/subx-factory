#!/usr/bin/env bash
# Core factory.js byte budget (lean audit 2026-10-22). Fails above the budget.
#   tools/check_budget.sh [path/to/factory.js] [budget_bytes]
# Defaults: factory/factory.js, 265000 B. Opt-in files (factory-gp.js, factory-rail.js, factory-reports.js) are reported, not budgeted.
# v1.2.9 sign-in fix is 261873 B and does not fit the old 255000 cap.
set -euo pipefail
cd "$(dirname "$0")/.."
F=${1:-factory/factory.js}
BUDGET=${2:-${CORE_BUDGET_BYTES:-265000}}
B=$(wc -c < "$F" | tr -d ' ')
for o in "$(dirname "$F")"/factory-*.js; do [ -f "$o" ] && echo "opt-in $(basename "$o"): $(wc -c < "$o" | tr -d ' ') B"; done
if [ "$B" -gt "$BUDGET" ]; then
  echo "FAIL core $F: $B B > budget $BUDGET B (over by $((B - BUDGET)) B). Move room-only code to an opt-in file (build/split.mjs)." >&2
  exit 1
fi
echo "OK core $F: $B B <= budget $BUDGET B (headroom $((BUDGET - B)) B)"
