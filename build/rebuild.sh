#!/usr/bin/env bash
# Reproduce factory/factory.js from its pinned sources (no secrets; gpchat is a public repo).
#   ours  = build/sources/template_factory_660144d1886e.js  (T0 template, hosted config, no inline key)
#   base  = jebbdykstra99/gpchat @ 7553762 factory.js
#   theirs= jebbdykstra99/gpchat PR #31 @ ${GP_PR31:-43a1936} factory.js  (hardened guards)
# Then resolve.py (8 conflicts) and fold.py (function-level fold + feature flags + skin keys), then split.mjs
# (opt-in files: factory-gp.js = gpchat-only features + F1 rail, factory-rail.js = NWS/CWF/BART live rails; core byte budget).
# Usage: build/rebuild.sh [--check]   (--check exits 1 if any output differs from factory/)
# Needs node_modules (npm install) for split.mjs.
set -euo pipefail
cd "$(dirname "$0")"
GP_PR31=${GP_PR31:-43a1936032e6ea2e54613257536b652920903905}
T=$(mktemp -d); trap 'rm -rf "$T" template.js base_gpchat_7553762.js gpchat_pr31.js merged_raw.js merged.js factory.js factory-gp.js factory-rail.js' EXIT
git clone -q https://github.com/jebbdykstra99/gpchat "$T/gp"
git -C "$T/gp" fetch -q origin "$GP_PR31" 2>/dev/null || git -C "$T/gp" fetch -q origin 'refs/pull/31/head'
git -C "$T/gp" show 7553762:factory.js > base_gpchat_7553762.js
git -C "$T/gp" show "$GP_PR31":factory.js > gpchat_pr31.js
cp sources/template_factory_660144d1886e.js template.js
cp template.js "$T/ours.js"
git merge-file -p "$T/ours.js" base_gpchat_7553762.js gpchat_pr31.js > merged_raw.js || true
python3 resolve.py >/dev/null
python3 fold.py >/dev/null
node --check factory.js
node split.mjs
OUT="factory.js factory-gp.js factory-rail.js"
for f in $OUT; do node --check "$f"; done
if [ "${1:-}" = --check ]; then
  for f in $OUT; do cmp "$f" "../factory/$f"; done && echo "rebuild: identical"
else
  for f in $OUT; do cp "$f" "../factory/$f"; done; (cd ../factory && sha256sum $OUT)
fi
