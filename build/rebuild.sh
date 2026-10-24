#!/usr/bin/env bash
# Reproduce factory/factory.js from its pinned sources (no secrets; gpchat is a public repo).
#   ours  = build/sources/template_factory_660144d1886e.js  (T0 template, hosted config, no inline key)
#   base  = gpchat @ 7553762 factory.js
#   theirs= gpchat PR #31 @ ${GP_PR31:-43a1936} factory.js  (hardened guards)
# Then resolve.py (8 conflicts) and fold.py (function-level fold + feature flags + skin keys), then split.mjs
# (opt-in files: factory-gp.js = gpchat-only features + F1 rail, factory-rail.js = NWS/CWF/BART live rails,
# factory-reports.js = report loop; core byte budget).
# Usage:
#   build/rebuild.sh [--overwrite]
#   build/rebuild.sh --check [--from DIR --against DIR]
# --check exits 0 and prints "rebuild: identical" only when every output matches.
# Each differing file is named on stderr and the exit status is 1 (a later match
# does not hide an earlier one).
# A plain run copies generated output onto factory/ when the bytes already match.
# If a committed file differs, the run stops and leaves it in place unless --overwrite
# is set. factory/*.js is generated, not an input: fold.py takes openAdminPicker()
# from the gpchat side of the merge, so a hand edit to the New message picker filter
# would otherwise be replaced with no warning.
# --from/--against compare two directories of the four output names and skip
# generation (test/rebuild-check.test.sh).
# Needs node_modules (npm install) for split.mjs.
set -euo pipefail

OUT=(factory.js factory-gp.js factory-rail.js factory-reports.js)
DIFFS=()

collect_diffs() {
  local gen_dir=$1 com_dir=$2 f
  DIFFS=()
  for f in "${OUT[@]}"; do
    if [ ! -f "$gen_dir/$f" ] || [ ! -f "$com_dir/$f" ] || ! cmp -s "$gen_dir/$f" "$com_dir/$f"; then
      DIFFS+=("$f")
    fi
  done
}

diff_stat() {
  git --no-pager diff --no-index --stat -- "$1" "$2" >&2 || true
}

finish_check() {
  local gen_dir=$1 com_dir=$2 f
  collect_diffs "$gen_dir" "$com_dir"
  if [ "${#DIFFS[@]}" -eq 0 ]; then
    echo "rebuild: identical"
    return 0
  fi
  for f in "${DIFFS[@]}"; do
    echo "rebuild: differs: factory/$f" >&2
    if [ -f "$gen_dir/$f" ] && [ -f "$com_dir/$f" ]; then
      diff_stat "$com_dir/$f" "$gen_dir/$f"
    fi
  done
  if [ "${#DIFFS[@]}" -eq 1 ]; then
    echo "rebuild: not identical (1 file differs)" >&2
  else
    echo "rebuild: not identical (${#DIFFS[@]} files differ)" >&2
  fi
  return 1
}

guard_write() {
  local gen_dir=$1 com_dir=$2 dest_dir=$3 overwrite=$4 f
  collect_diffs "$gen_dir" "$com_dir"
  if [ "${#DIFFS[@]}" -ne 0 ]; then
    for f in "${DIFFS[@]}"; do
      echo "rebuild: would overwrite: factory/$f" >&2
      if [ -f "$gen_dir/$f" ] && [ -f "$com_dir/$f" ]; then
        diff_stat "$com_dir/$f" "$gen_dir/$f"
      fi
    done
    if [ "$overwrite" -ne 1 ]; then
      if [ "${#DIFFS[@]}" -eq 1 ]; then
        echo "rebuild: refusing to overwrite 1 committed file." >&2
      else
        echo "rebuild: refusing to overwrite ${#DIFFS[@]} committed files." >&2
      fi
      echo "rebuild: factory/*.js is generated output, not an input. openAdminPicker() (the DM New message picker, including its user filter) is folded from the gpchat sources, so a hand edit there would be replaced." >&2
      echo "rebuild: committed files were left unchanged. Pass --overwrite to replace them with generated output." >&2
      return 1
    fi
    echo "rebuild: --overwrite set; replacing committed files with generated output." >&2
  fi
  for f in "${OUT[@]}"; do
    cp "$gen_dir/$f" "$dest_dir/$f" || return 1
  done
  return 0
}

main() {
  local mode=write overwrite=0 from= against= script_dir
  while [ $# -gt 0 ]; do
    case "$1" in
      --check) mode=check ;;
      --overwrite) overwrite=1 ;;
      --from)
        if [ $# -lt 2 ]; then echo "rebuild: --from needs a directory" >&2; exit 2; fi
        shift
        from=$1
        ;;
      --against)
        if [ $# -lt 2 ]; then echo "rebuild: --against needs a directory" >&2; exit 2; fi
        shift
        against=$1
        ;;
      *)
        echo "rebuild: unknown argument: $1" >&2
        exit 2
        ;;
    esac
    shift
  done
  if [ "$mode" = check ] && [ "$overwrite" -eq 1 ]; then
    echo "rebuild: --overwrite cannot be combined with --check" >&2
    exit 2
  fi
  if [ -n "$from" ] || [ -n "$against" ]; then
    if [ "$mode" != check ] || [ -z "$from" ] || [ -z "$against" ]; then
      echo "rebuild: --from and --against are only valid together with --check" >&2
      exit 2
    fi
    if [ ! -d "$from" ] || [ ! -d "$against" ]; then
      echo "rebuild: --from and --against must be directories" >&2
      exit 2
    fi
    from=$(cd "$from" && pwd)
    against=$(cd "$against" && pwd)
    if finish_check "$from" "$against"; then exit 0; fi
    exit 1
  fi

  script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  cd "$script_dir"
  local GP_PR31=${GP_PR31:-43a1936032e6ea2e54613257536b652920903905}
  # T stays global. The EXIT trap runs after main returns, and a local is
  # already gone by then; with set -u that failed the script even when the
  # copy itself succeeded.
  T=$(mktemp -d)
  trap 'rm -rf "${T:-}" template.js base_gpchat_7553762.js gpchat_pr31.js merged_raw.js merged.js factory.js factory-gp.js factory-rail.js factory-reports.js' EXIT
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
  local f
  for f in "${OUT[@]}"; do node --check "$f"; done
  if [ "$mode" = check ]; then
    if finish_check . ../factory; then exit 0; fi
    exit 1
  fi
  guard_write . ../factory ../factory "$overwrite" || exit 1
  (cd ../factory && sha256sum "${OUT[@]}")
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
