#!/usr/bin/env python3
"""Shared pinned shell: per-room declaration check (read-only).

  python3 tools/shell_drift.py ROOM_DIR [ROOM_DIR ...] [--shell-root shell] [--json OUT] [--md OUT] [--strict]

A room may differ from the pinned shell only through DECLARED layers in its site.json "shell" block:
  1. config      site.json keys (features, skin, rail, nests, minAge, imageUploads, ...)   always allowed
  2. overrides   theme (CSS/assets), copy (site.json keys or a copy file), legal (per-room pages, never touched
                 by the shell), modules (extension files through documented hooks, sha256-pinned)
  3. fork        a full room copy of factory.js pinned to a named base version, with its sha256 and a reason
Anything else is DRIFT: a local factory.js that is not a declared fork, a shell <script> that is not pinned by
full commit SHA with the integrity from shell/<base>/SHELL.json, or a local script that is not declared.

Never writes to the room, Firestore, or the network. Exit 1 with --strict when any room has DRIFT.
"""
import argparse, glob, hashlib, json, os, re, subprocess, sys

PIN_RE = re.compile(r'^https://(?:cdn|fastly)\.jsdelivr\.net/gh/jebbdykstra99/subx-factory@([0-9a-f]{40})/shell/(v[0-9.]+)/(factory(?:-[a-z]+)?\.js)$')
# Same bytes before shell/vX.Y.Z merges: factory/ at the release's SHELL.json sourceCommit.
PRE_RE = re.compile(r'^https://(?:cdn|fastly)\.jsdelivr\.net/gh/jebbdykstra99/subx-factory@([0-9a-f]{40})/factory/(factory(?:-[a-z]+)?\.js)$')
THIRD_PARTY = (re.compile(r'^https://www\.gstatic\.com/firebasejs/10\.12\.2/firebase-[a-z-]+-compat\.js$'),
               re.compile(r'^https://cdn\.jsdelivr\.net/npm/emoji-picker-element@1/index\.js$'))
SCRIPT_RE = re.compile(r'<script\b([^>]*)>', re.I)
ATTR_RE = re.compile(r'([a-zA-Z-]+)\s*=\s*"([^"]*)"')
SHELL_FILES = ('factory.js', 'factory-gp.js', 'factory-rail.js', 'factory-reports.js')


def sha256(p):
    with open(p, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def manifests(root):
    out = {}
    for p in glob.glob(os.path.join(root, 'v*', 'SHELL.json')):
        m = json.load(open(p))
        m['_dir'] = os.path.dirname(p)
        out[m['version']] = m
    return out


def diff_lines(a, b):
    r = subprocess.run(['diff', a, b], capture_output=True, text=True)
    return sum(1 for l in r.stdout.splitlines() if l[:1] in '<>')


def scripts(room):
    """[(page, index, src, integrity, crossorigin)] for every <script src> in top-level and one-level-deep pages."""
    out = []
    pages = sorted(glob.glob(os.path.join(room, '*.html')) + glob.glob(os.path.join(room, '*', '*.html')))
    for page in pages:
        html = open(page, encoding='utf-8', errors='replace').read()
        for i, m in enumerate(SCRIPT_RE.finditer(html)):
            a = dict((k.lower(), v) for k, v in ATTR_RE.findall(m.group(1)))
            if 'src' in a:
                out.append((os.path.relpath(page, room), i, a['src'], a.get('integrity'), a.get('crossorigin')))
    return out


def check(room, mans):
    name = os.path.basename(os.path.normpath(room))
    try:
        site = json.load(open(os.path.join(room, 'site.json')))
    except Exception as e:
        return {'room': name, 'status': 'DRIFT', 'findings': ['site.json unreadable: %s' % e], 'layers': {}}
    sh = site.get('shell') if isinstance(site.get('shell'), dict) else None
    f, layers = [], {}
    local = os.path.join(room, 'factory.js')
    local_sha = sha256(local) if os.path.isfile(local) else None
    if sh is None:
        f.append('no site.json "shell" block (legacy per-room copy, undeclared)')
        if local_sha:
            hit = [v for v, m in mans.items() if m['files']['factory.js']['sha256'] == local_sha]
            f.append('local factory.js sha256 %s = %s' % (local_sha[:8], hit[0] if hit else 'no pinned release'))
        return {'room': name, 'status': 'DRIFT', 'findings': f, 'layers': layers, 'localSha': local_sha}
    base = sh.get('base')
    man = mans.get(base)
    if not man:
        f.append('shell.base %r has no shell/%s/SHELL.json' % (base, base))
    ov = sh.get('overrides') or {}
    declared_modules = {}
    for mod in ov.get('modules') or []:
        p = os.path.join(room, mod.get('file', ''))
        if not os.path.isfile(p):
            f.append('module %s declared but missing' % mod.get('file'))
        elif mod.get('sha256') != sha256(p):
            f.append('module %s sha256 differs from declaration' % mod.get('file'))
        if not mod.get('reason'):
            f.append('module %s has no reason' % mod.get('file'))
        declared_modules[mod.get('file')] = mod
    layers['modules'] = sorted(declared_modules)
    for layer in ('theme', 'copy', 'legal'):
        items = ov.get(layer) or []
        layers[layer] = items
        for it in items:
            path = it.split(':', 1)[0].split('#', 1)[0]
            if path and not os.path.exists(os.path.join(room, path)):
                f.append('%s override %s missing' % (layer, it))
    keep = set(sh.get('keep') or [])       # room files that are not shell code (gate.js, takedown.js, ref.js ...)
    fork = bool(sh.get('fork'))
    layers['fork'] = fork
    shell_tags = []
    for page, i, src, integ, xo in scripts(room):
        clean = src.split('?', 1)[0]
        if any(r.match(src) for r in THIRD_PARTY):
            continue
        m = PIN_RE.match(src)
        pre = PRE_RE.match(src)
        if pre and man and pre.group(1) == man.get('sourceCommit'):
            m = pre
        if m:
            if m is pre:
                ver, fn = base, pre.group(2)
            else:
                sha, ver, fn = m.groups()
            shell_tags.append((page, fn))
            if ver != base:
                f.append('%s loads shell %s but shell.base is %s' % (page, ver, base))
            elif man and man['files'].get(fn, {}).get('integrity') != integ:
                f.append('%s %s: integrity missing or not the SHELL.json value' % (page, fn))
            if xo != 'anonymous':
                f.append('%s %s: crossorigin="anonymous" required for SRI' % (page, fn))
            continue
        if src.startswith('http'):
            f.append('%s loads undeclared remote script %s' % (page, src))
            continue
        rel = clean.lstrip('/')
        if rel in SHELL_FILES:
            if fork and rel == sh.get('file', 'factory.js'):
                shell_tags.append((page, rel))
                continue
            f.append('%s loads local %s (not a declared fork)' % (page, rel))
        elif rel in declared_modules or rel in keep:
            continue
        else:
            f.append('%s loads undeclared local script %s' % (page, rel))
    if fork:
        for k in ('reason', 'sha256'):
            if not sh.get(k):
                f.append('fork without shell.%s' % k)
        if not sh.get('exception'):
            f.append('fork without shell.exception (EXCEPTIONS.md row)')
        p = os.path.join(room, sh.get('file', 'factory.js'))
        if not os.path.isfile(p):
            f.append('fork file %s missing' % sh.get('file', 'factory.js'))
        else:
            got = sha256(p)
            if got != sh.get('sha256'):
                f.append('fork file sha256 %s != declared %s (undeclared edit)' % (got[:8], str(sh.get('sha256'))[:8]))
            if man:
                layers['forkDiffLines'] = diff_lines(os.path.join(man['_dir'], 'factory.js'), p)
    else:
        if local_sha:
            f.append('stale local factory.js present while shell.fork is false (delete it)')
        if not any(fn == 'factory.js' for _, fn in shell_tags):
            f.append('no pinned factory.js <script> found')
    return {'room': name, 'status': 'DRIFT' if f else ('FORK' if fork else 'OK'), 'base': base,
            'findings': f, 'layers': layers, 'localSha': local_sha}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rooms', nargs='+')
    ap.add_argument('--shell-root', default=os.path.join(os.path.dirname(__file__), '..', 'shell'))
    ap.add_argument('--json')
    ap.add_argument('--md')
    ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()
    mans = manifests(a.shell_root)
    res = [check(r, mans) for r in a.rooms]
    lines = ['| Room | Status | Base | Declared layers | Findings |', '|---|---|---|---|---|']
    for r in res:
        lay = ', '.join('%s=%s' % (k, v) for k, v in r['layers'].items() if v) or '-'
        lines.append('| %s | %s | %s | %s | %s |' % (r['room'], r['status'], r.get('base') or '-', lay, '; '.join(r['findings']) or '-'))
    md = '\n'.join(lines) + '\n'
    print(md)
    if a.md:
        open(a.md, 'w').write(md)
    if a.json:
        json.dump(res, open(a.json, 'w'), indent=2)
    if a.strict and any(r['status'] == 'DRIFT' for r in res):
        sys.exit(1)


if __name__ == '__main__':
    main()
