#!/usr/bin/env bash
# build/rebuild.sh --check must fail when any compared file differs, including
# a file that is not the last one, and pass only when every file matches.
# Also checks the write guard: a differing committed file is left in place
# unless --overwrite is passed.
set -euo pipefail
cd "$(dirname "$0")/.."

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
gen="$tmp/gen"
com="$tmp/com"
work="$tmp/work"
mkdir -p "$gen" "$com" "$work"
files=(factory.js factory-gp.js factory-rail.js factory-reports.js)

reset_pair() {
  local f
  for f in "${files[@]}"; do
    printf 'base %s\n' "$f" > "$gen/$f"
    printf 'base %s\n' "$f" > "$com/$f"
  done
}
reset_pair

run_check() {
  set +e
  bash build/rebuild.sh --check --from "$gen" --against "$com" >"$tmp/out" 2>"$tmp/err"
  rc=$?
  set -e
}

fail() {
  echo "FAIL: $1" >&2
  echo "--- stdout ---" >&2
  cat "$tmp/out" >&2 || true
  echo "--- stderr ---" >&2
  cat "$tmp/err" >&2 || true
  exit 1
}

assert_pass() {
  run_check
  [ "$rc" -eq 0 ] || fail "expected exit 0, got $rc"
  grep -qx 'rebuild: identical' "$tmp/out" || fail "missing identical marker"
  if grep -q 'differs:' "$tmp/err"; then
    fail "pass case named a differing file"
  fi
}

assert_fail() {
  run_check
  [ "$rc" -ne 0 ] || fail "expected non-zero exit when files differ"
  if grep -qx 'rebuild: identical' "$tmp/out"; then
    fail "differing files were reported as identical"
  fi
  grep -q 'rebuild: not identical' "$tmp/err" || fail "missing not-identical summary"
  local name
  for name in "$@"; do
    grep -qx "rebuild: differs: factory/$name" "$tmp/err" || fail "missing differ line for $name"
  done
}

echo "1. all four files match"
assert_pass

echo "2. a non-last file differs (factory-gp.js); the last file still matches"
printf 'hand edit in picker filter\n' > "$com/factory-gp.js"
assert_fail factory-gp.js
if grep -q 'factory/factory-reports.js' "$tmp/err"; then
  fail "matched last file was reported as differing"
fi
# --check must not rewrite the committed side
grep -qx 'hand edit in picker filter' "$com/factory-gp.js" || fail "--check rewrote the committed file"

echo "3. first three differ and the last matches (previously reported identical)"
printf 'edit core\n' > "$com/factory.js"
printf 'edit rail\n' > "$com/factory-rail.js"
assert_fail factory.js factory-gp.js factory-rail.js
if grep -q 'factory/factory-reports.js' "$tmp/err"; then
  fail "matched last file was reported as differing"
fi
# every earlier name is present, not only whichever cmp ran last
grep -qx 'rebuild: differs: factory/factory.js' "$tmp/err" || fail "missing first file"
grep -qx 'rebuild: differs: factory/factory-gp.js' "$tmp/err" || fail "missing second file"
grep -qx 'rebuild: differs: factory/factory-rail.js' "$tmp/err" || fail "missing third file"

echo "4. only the last file differs"
reset_pair
printf 'edit reports\n' > "$com/factory-reports.js"
assert_fail factory-reports.js
if grep -q 'factory/factory.js' "$tmp/err"; then
  fail "matched earlier file was reported as differing"
fi

echo "5. all match again after the committed copies are restored"
reset_pair
assert_pass

echo "6. write guard keeps a non-last local edit unless --overwrite is set"
# shellcheck disable=SC1091
source build/rebuild.sh
reset_pair
printf 'local openAdminPicker filter\n' > "$com/factory.js"
rm -rf "$work"
mkdir -p "$work"
cp -a "$com/." "$work/"
before=$(cat "$work/factory.js")
set +e
guard_write "$gen" "$work" "$work" 0 >"$tmp/out" 2>"$tmp/err"
rc=$?
set -e
[ "$rc" -ne 0 ] || fail "write should refuse when a committed file differs"
[ "$(cat "$work/factory.js")" = "$before" ] || fail "refused write still changed the committed file"
grep -qx 'rebuild: would overwrite: factory/factory.js' "$tmp/err" || fail "refusal did not name factory.js"
grep -q 'left unchanged' "$tmp/err" || fail "refusal did not say the files were left unchanged"
if grep -qx 'rebuild: identical' "$tmp/out"; then
  fail "refused write claimed identical"
fi
guard_write "$gen" "$work" "$work" 1 >"$tmp/out" 2>"$tmp/err"
cmp -s "$gen/factory.js" "$work/factory.js" || fail "--overwrite did not replace factory.js"
grep -q 'replacing committed files' "$tmp/err" || fail "--overwrite was not announced"
# an already-matching tree writes without --overwrite
guard_write "$gen" "$work" "$work" 0 >"$tmp/out" 2>"$tmp/err"
cmp -s "$gen/factory.js" "$work/factory.js" || fail "matching write changed factory.js"

echo "rebuild-check: ok"
