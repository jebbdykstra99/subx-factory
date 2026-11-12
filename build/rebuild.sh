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
  # 27chat #51 sign-in loop. The reviewed diff is against the split core at blob
  # 7463cba (shell v1.2.8), so it is applied after split.mjs, not in the template.
  if ! patch --forward --batch -p1 -i signin-loop.patch; then
    echo "rebuild: sign-in loop patch failed. The split core no longer matches blob 7463cba." >&2
    exit 1
  fi
  rm -f factory.js.orig
  # Review fixes on top of the frozen signin-loop.patch: the lazy sign-in host
  # exposes isLiveUser and closeAuth so onRegister can close the sheet when
  # the user is already signed in. The patch file is not in this change set.
  python3 -c '
import pathlib, sys
p = pathlib.Path("factory.js")
t = p.read_text()
old = """        composeErr: composeErr,
        setAuthOpenWhenReady: function (v) { authOpenWhenReady = !!v; }"""
new = """        composeErr: composeErr,
        isLiveUser: isLiveUser,
        closeAuth: closeAuth,
        setAuthOpenWhenReady: function (v) { authOpenWhenReady = !!v; }"""
if new in t:
    pass
elif old in t:
    p.write_text(t.replace(old, new, 1))
else:
    sys.exit("rebuild: sign-in host object did not match; cannot add isLiveUser/closeAuth")
'
  # v1.2.10: preload factory-signin.js on pointerdown/touchstart of Sign in
  # so a Google tap can call signInWithPopup in the same gesture.
  python3 -c '
import pathlib, sys
p = pathlib.Path("factory.js")
t = p.read_text()
q = chr(39)
old = "  function wireEvents() {\n   document.addEventListener(" + q + "click" + q + ", function (e) {"
new = "  function wireEvents() {\n    [" + q + "pointerdown" + q + "," + q + "touchstart" + q + "].forEach(function(v){document.addEventListener(v,function(e){try{if(e.target.closest(" + q + "#auth-signin,#profile-signin-prompt-btn,#cv-google-login" + q + "))loadSigninModule()}catch(x){}},{passive:true});});\n   document.addEventListener(" + q + "click" + q + ", function (e) {"
if new in t:
    pass
elif old in t:
    p.write_text(t.replace(old, new, 1))
else:
    sys.exit("rebuild: wireEvents() did not match; cannot add sign-in preload")
'
  # v1.2.10: fold simple style tags into addCss, inject the SubX cat link,
  # and squeeze blank lines before top-level functions so the core still
  # fits the 255000 B cap.
  python3 - << 'APPLY_CAT'
# Apply v1.2.10 addCss refactor, SubX cat inject, and function-blank squeeze.
# Reads and writes factory.js in the current directory (build/).
from pathlib import Path
import re

p = Path('factory.js')
t = p.read_text()
if 'function ensureSubxCat()' in t:
    raise SystemExit(0)

def skip_string(s, i):
    q = s[i]; i += 1
    while i < len(s):
        if s[i] == '\\':
            i += 2
            continue
        if s[i] == q:
            return i + 1
        i += 1
    return i

def assignment_semicolon(s, start):
    i = start
    while i < len(s):
        if s[i] in "'\"":
            i = skip_string(s, i)
            continue
        if s[i] == ';':
            return i
        i += 1
    return -1

ADD_CSS = "  function addCss(id,c){if(document.getElementById(id))return;var s=document.createElement('style');s.id=id;s.textContent=c;document.head.appendChild(s);}\n"
hook = "  'use strict';\n\n"
if ADD_CSS not in t:
    if t.count(hook) != 1:
        raise SystemExit('rebuild: use strict hook not unique; cannot add addCss')
    t = t.replace(hook, hook + ADD_CSS, 1)

pos = 0
while True:
    j = t.find("var st = document.createElement('style');", pos)
    if j < 0:
        break
    id_m = re.search(r"st\.id = '([^']+)';", t[j:j+120])
    if not id_m:
        raise SystemExit('rebuild: style tag without id')
    css_id = id_m.group(1)
    if css_id == 'acc-gate-css':
        pos = j + 1
        continue
    tc = t.find('st.textContent =', j)
    if tc < 0:
        raise SystemExit('rebuild: style tag without textContent')
    expr_start = tc + len('st.textContent =')
    semi = assignment_semicolon(t, expr_start)
    if semi < 0:
        raise SystemExit('rebuild: style assignment has no semicolon')
    expr = t[expr_start:semi].strip()
    after = t[semi+1:]
    next_m = re.search(r'\S', after)
    next_stmt = after[next_m.start():] if next_m else ''
    if not next_stmt.startswith('document.head.appendChild(st);'):
        pos = semi + 1
        continue
    app = semi + 1 + after.find('document.head.appendChild(st);')
    line_start = t.rfind('\n', 0, app) + 1
    indent = t[line_start:app]
    var_line_start = t.rfind('\n', 0, j) + 1
    block_start = var_line_start
    prefix = ''
    prev_nl = t.rfind('\n', 0, var_line_start-1)
    prev_line = t[prev_nl+1:var_line_start]
    if re.search(r"if \(document\.getElementById\('%s'\)\) return;" % re.escape(css_id), prev_line):
        block_start = prev_nl + 1
    elif re.search(r"if \(!document\.getElementById\('%s'\)\) \{" % re.escape(css_id), prev_line):
        block_start = prev_nl + 1
    elif css_id == 'acc-gate-css':
        k = t.rfind("if (o || document.getElementById('acc-gate-css')) return;", 0, j)
        if k < 0:
            raise SystemExit('rebuild: acc-gate guard not found')
        block_start = k
        prefix = t[block_start:var_line_start].replace(
            "if (o || document.getElementById('acc-gate-css')) return;",
            "if (o) return;"
        )
    end = app + len('document.head.appendChild(st);')
    opened = t[block_start:j]
    if re.search(r"if \(!document\.getElementById\('%s'\)\) \{" % re.escape(css_id), opened):
        m_end = re.match(r'\s*\}', t[end:])
        if not m_end:
            raise SystemExit('rebuild: share-sheet style block missing close')
        end = end + m_end.end()
    if css_id == 'acc-gate-css' and prefix:
        replacement = prefix + f"{indent}addCss('{css_id}', {expr});"
    else:
        replacement = f"{indent}addCss('{css_id}', {expr});"
    t = t[:block_start] + replacement + t[end:]
    pos = block_start + len(replacement)

CAT = "  function ensureSubxCat(){var a=document.querySelector('.subx-cat-link'),m,h,r,u='url(https://subx.it/assets/brand/cat-mask.png) center/contain no-repeat';if(!a){m=document.querySelector('.sidebar-brand .brand-mark');if(!m)return;a=document.createElement('a');a.href='https://subx.it/';a.className='subx-cat-link';a.setAttribute('aria-label','SubX home');a.style.cssText='display:inline-flex;align-items:center;justify-content:center;width:44px;height:44px;z-index:600;text-decoration:none;color:var(--nav-text,#fff)';a.innerHTML='<span style=\"width:28px;height:28px;background:currentColor;-webkit-mask:'+u+';mask:'+u+'\"></span>';m.parentNode.insertBefore(a,m)}h=document.getElementById('hamburger');if(h&&innerWidth<=MOBILE_NAV_MQ){r=h.getBoundingClientRect();a.style.position='fixed';a.style.top=r.top+'px';a.style.left=r.right+4+'px';a.style.background='var(--nav-bg,#111)'}else if(a){a.style.position=''}if(!ensureSubxCat.w){ensureSubxCat.w=1;addEventListener('resize',ensureSubxCat)}}\n"
hook2 = '  function applySiteChrome() {\n    if (!site) return;\n'
if hook2 not in t:
    raise SystemExit('rebuild: applySiteChrome hook not found; cannot add SubX cat')
if 'function ensureSubxCat()' not in t:
    t = t.replace(hook2, CAT + '  function applySiteChrome() {\n    ensureSubxCat();\n    if (!site) return;\n', 1)
hook3 = "  function wireEvents() {\n    ['pointerdown','touchstart']"
if hook3 in t and "function wireEvents() {\n    ensureSubxCat();\n    ['pointerdown','touchstart']" not in t:
    t = t.replace(hook3, "  function wireEvents() {\n    ensureSubxCat();\n    ['pointerdown','touchstart']", 1)
t = re.sub(r'\n\n(  function )', r'\n\1', t)
t = t.replace('function (', 'function(')
p.write_text(t)
APPLY_CAT
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
