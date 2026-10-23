#!/usr/bin/env bash
# Swap the whoMark disclosure-mark family in ONE command. See README "Swapping the disclosure mark family".
set -euo pipefail
usage() {
  cat <<'U'
usage: ./swap-marks.sh <family-dir> [--dry-run] [--no-pr] [--base <ref>] [--branch <name>]

  <family-dir>   folder with exactly the two family inputs: sprite.svg + config.json (e.g. marks/placeholder-square)
  --dry-run      validate + print the diff (files and sizes) against assets/whomark/; writes nothing, pushes nothing
  --no-pr        do the real swap on a new local branch (build, tests, commit) but do not push or open a PR
  --base <ref>   branch point for the swap branch (default: origin/main)
  --branch <n>   branch name (default: cursor/whomark-family-<family>-<YYYYMMDD-HHMM>)

Steps: (1) validate the family: human/ai/hybrid + -sm symbols, every <symbol> parses with viewBox 0 0 24 24 and
<title>, config fields complete, policy labels unchanged, asset byte budgets, factory/factory.js <= 255,000 B;
(2) copy sprite.svg + config.json into assets/whomark/, regenerate whomark.js config + og/corner PNGs, rebuild
factory/ via build/rebuild.sh (build/fold.py), run every test; (3) commit as Cursor Agent on a new branch, push with
the gh credential helper and open ONE draft PR in subx-factory for two-key CLEAR. Never merges, never stamps rooms
(rooms pick the new family up on their next normal stamp). Needs: python3 + cairosvg, node + npm install, gh.
U
}
FAM=''; DRY=0; NOPR=0; BASE=origin/main; BRANCH=''
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --dry-run) DRY=1 ;;
    --no-pr) NOPR=1 ;;
    --base) BASE=${2:?--base needs a ref}; shift ;;
    --branch) BRANCH=${2:?--branch needs a name}; shift ;;
    -*) echo "unknown option $1" >&2; usage >&2; exit 2 ;;
    *) [ -z "$FAM" ] || { echo "one family dir only" >&2; exit 2; }; FAM=$1 ;;
  esac
  shift
done
[ -n "$FAM" ] || { usage >&2; exit 2; }
[ -d "$FAM" ] || { echo "not a directory: $FAM" >&2; exit 2; }
FAM=$(cd "$FAM" && pwd)
ROOT=$(cd "$(dirname "$0")" && pwd); cd "$ROOT"
A=assets/whomark
NAME=$(python3 -c 'import json,sys,re; print(re.sub(r"[^a-z0-9-]+","-",json.load(open(sys.argv[1]))["family"].lower()).strip("-") or "family")' "$FAM/config.json" 2>/dev/null || echo family)

echo "== 1/3 validate $FAM"
python3 build/whomark.py --validate "$FAM"
tools/check_budget.sh

if [ $DRY = 1 ]; then
  T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
  cp -R "$A" "$T/new"
  PNG=; python3 -c 'import cairosvg' 2>/dev/null || { PNG=--no-png; echo "(cairosvg missing: PNGs not re-rendered in this dry run)"; }
  python3 build/whomark.py --src "$FAM" --out "$T/new" $PNG >/dev/null
  echo "== dry run: assets/whomark/ diff (nothing written, nothing pushed)"
  python3 - "$A" "$T/new" <<'PY'
import os, sys
a, b = sys.argv[1], sys.argv[2]
fa = {f: os.path.getsize(os.path.join(a, f)) for f in os.listdir(a)}
fb = {f: os.path.getsize(os.path.join(b, f)) for f in os.listdir(b)}
ch = 0
print('%-8s %-20s %9s %9s %8s' % ('status', 'file', 'old B', 'new B', 'delta'))
for f in sorted(set(fa) | set(fb)):
    o, n = fa.get(f), fb.get(f)
    same = o is not None and n is not None and open(os.path.join(a, f), 'rb').read() == open(os.path.join(b, f), 'rb').read()
    st = 'same' if same else ('added' if o is None else ('removed' if n is None else 'changed'))
    ch += st != 'same'
    print('%-8s %-20s %9s %9s %+8d' % (st, f, o if o is not None else '-', n if n is not None else '-', (n or 0) - (o or 0)))
print('%-8s %-20s %9d %9d %+8d   (budget 65536 B)' % ('total', '', sum(fa.values()), sum(fb.values()), sum(fb.values()) - sum(fa.values())))
print('%d file(s) would change. factory/factory.js unchanged by a swap (%d B).' % (ch, os.path.getsize('factory/factory.js')))
PY
  { git --no-pager diff --no-index --stat=100 -- "$A" "$T/new" || true; } | sed "s#$T/new#(new)#g"
  exit 0
fi

echo "== 2/3 swap + rebuild + tests"
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "working tree not clean; commit or stash first" >&2; exit 1; }
[ -n "$BRANCH" ] || BRANCH="cursor/whomark-family-$NAME-$(date +%Y%m%d-%H%M)"
git rev-parse --verify -q "$BASE" >/dev/null || { echo "base $BASE not found (git fetch origin?)" >&2; exit 1; }
git show-ref --verify -q "refs/heads/$BRANCH" && { echo "branch $BRANCH exists" >&2; exit 1; }
git checkout -q -b "$BRANCH" "$BASE"
cp "$FAM/sprite.svg" "$FAM/config.json" "$A/"
python3 build/whomark.py
build/rebuild.sh >/dev/null
python3 build/whomark.py --check
npm run -s check
node test/whomark.test.js
build/rebuild.sh --check
tools/check_budget.sh
if [ -z "$(git status --porcelain -- "$A" factory)" ]; then echo "no change: $FAM is already the active family"; exit 0; fi

echo "== 3/3 commit"
git add -A "$A" factory
git -c user.name='Cursor Agent' -c user.email='cursoragent@cursor.com' commit -q \
  -m "whoMark: swap disclosure mark family to $NAME" -m "One-command swap (./swap-marks.sh). Sprite + config only; rooms pick it up on the next normal stamp. Two-key CLEAR before merge."
git --no-pager log -1 --stat --format='%H %s'
if [ $NOPR = 1 ]; then echo "--no-pr: committed on local branch $BRANCH; not pushed, no PR"; exit 0; fi
git -c credential.helper= -c "credential.helper=!$(command -v gh) auth git-credential" push origin HEAD
gh pr create --draft --base "${BASE#origin/}" --head "$BRANCH" \
  --title "whoMark: swap disclosure mark family to $NAME (two-key CLEAR)" \
  --body "Swapped by \`./swap-marks.sh\`: assets/whomark/sprite.svg + config.json from \`${FAM#$ROOT/}\`, regenerated whomark.js config block and og/corner PNGs, rebuilt factory/, all tests green. No per-room edits; rooms pick this up on their next normal stamp (site.json \`whoMark: true\` rooms only). **Two-key CLEAR required. Do not auto-merge.**"
