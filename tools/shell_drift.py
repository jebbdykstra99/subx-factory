#!/usr/bin/env python3
"""Shared pinned shell: per-room declaration check (read-only).

  python3 tools/shell_drift.py ROOM_DIR [ROOM_DIR ...] [--shell-root shell] [--json OUT] [--md OUT] [--strict] [--suggest]

A room may differ from the pinned shell only through DECLARED layers in its site.json "shell" block:
  1. config      site.json keys (features, skin, rail, nests, minAge, imageUploads, ...)   always allowed
  2. overrides   theme, copy, legal (files must exist), modules (local JS through documented hooks, sha256-pinned),
                 inline (each executable inline <script>, sha256 of its exact text, per page)
  3. fork        a full room copy of factory.js pinned to a named base version, with its sha256 and a reason
  keep           room scripts that are not shell code (gate.js, takedown.js ...), each sha256-pinned
Anything else is DRIFT. Status per room: OK, WARN (OK + non-blocking notes), FORK (declared fork), DRIFT.

Pages are parsed with html.parser (quoted, single-quoted and unquoted attributes; comments ignored), and every
*.html / *.htm under the room is scanned (except .git, node_modules, dot-dirs). Runtime script injection
(createElement('script'), import(), importScripts, document.write('<script')) in inline or local JS is DRIFT unless
the declaring entry carries "injects": "<reason>"; injection that names a factory/shell file is always DRIFT.
Any local .js that is a shell copy (release hash or SubX factory header) and is not the declared fork is DRIFT.

Never writes to the room, Firestore, or the network. Exit 1 with --strict when any room has DRIFT.
"""
import argparse, glob, hashlib, json, os, posixpath, re, subprocess, sys
from html.parser import HTMLParser

PIN_RE = re.compile(r'^https://cdn\.jsdelivr\.net/gh/jebbdykstra99/subx-factory@([0-9a-f]{40})/shell/(v[0-9.]+)/(factory(?:-[a-z]+)?\.js)$')
# Same bytes before shell/vX.Y.Z merges: factory/ at the release's SHELL.json sourceCommit.
PRE_RE = re.compile(r'^https://cdn\.jsdelivr\.net/gh/jebbdykstra99/subx-factory@([0-9a-f]{40})/factory/(factory(?:-[a-z]+)?\.js)$')
FIREBASE_RE = re.compile(r'^https://www\.gstatic\.com/firebasejs/10\.12\.2/firebase-[a-z-]+-compat\.js$')
EMOJI_RE = re.compile(r'^https://cdn\.jsdelivr\.net/npm/emoji-picker-element@([^/]+)/index\.js$')
EXACT_VER = re.compile(r'^\d+\.\d+\.\d+$')
SHELL_FILES = ('factory.js', 'factory-gp.js', 'factory-rail.js', 'factory-reports.js')
DATA_TYPES = ('application/ld+json', 'application/json', 'text/template', 'text/x-template')
INJECT_RE = re.compile(r"""createElement\s*\(\s*['"`]script['"`]\s*\)|\bimport\s*\(|\bimportScripts\s*\(|document\s*\.\s*write(?:ln)?\s*\([^)]*<\s*script""", re.I)
SHELL_REF_RE = re.compile(r'factory(?:-[a-z]+)?\.js|subx-factory|/shell/v\d', re.I)
SHELL_HEADER_RE = re.compile(r'/\*\s*SubX factory(?:-[a-z]+)?\.js\b')
SKIP_DIRS = {'.git', 'node_modules'}


def sha256b(b):
    return hashlib.sha256(b).hexdigest()


def sha256(p):
    with open(p, 'rb') as f:
        return sha256b(f.read())


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


class _Scripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out, self._cur = [], None

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self._cur = {'attrs': {k.lower(): (v if v is not None else '') for k, v in attrs}, 'text': [], 'line': self.getpos()[0]}

    def handle_startendtag(self, tag, attrs):
        if tag == 'script':
            self.out.append({'attrs': {k.lower(): (v if v is not None else '') for k, v in attrs}, 'text': '', 'line': self.getpos()[0]})

    def handle_data(self, data):
        if self._cur is not None:
            self._cur['text'].append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self._cur is not None:
            self._cur['text'] = ''.join(self._cur['text'])
            self.out.append(self._cur)
            self._cur = None


def walk(room, exts):
    for d, dirs, files in os.walk(room):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith('.'))
        for fn in sorted(files):
            if fn.lower().endswith(exts):
                yield os.path.join(d, fn)


def scripts(room):
    """Every <script> in every page: dicts with page, line, attrs, text. Comments are not scripts."""
    out = []
    for page in walk(room, ('.html', '.htm')):
        p = _Scripts()
        p.feed(open(page, encoding='utf-8', errors='replace').read())
        p.close()
        for s in p.out:
            s['page'] = os.path.relpath(page, room).replace(os.sep, '/')
            out.append(s)
    return out


def local_ref(page, src):
    """Room-relative posix path for a local src, or None if it escapes the room."""
    clean = src.split('#', 1)[0].split('?', 1)[0]
    if clean.startswith('/'):
        rel = posixpath.normpath(clean.lstrip('/'))
    else:
        rel = posixpath.normpath(posixpath.join(posixpath.dirname(page), clean))
    return None if rel.startswith('..') else rel


def injection_findings(text, where, allowed):
    f = []
    for m in INJECT_RE.finditer(text):
        window = text[max(0, m.start() - 200): m.end() + 300]
        if SHELL_REF_RE.search(window):
            f.append('%s injects a script that names a factory/shell file at runtime' % where)
        elif not allowed:
            f.append('%s injects a script at runtime (%s) without a declared "injects" reason' % (where, m.group(0)[:40]))
    return sorted(set(f))


def shell_hashes(mans):
    return {meta['sha256'] for m in mans.values() for meta in m['files'].values()}


def check(room, mans):
    name = os.path.basename(os.path.normpath(room))
    try:
        site = json.load(open(os.path.join(room, 'site.json')))
    except Exception as e:
        return {'room': name, 'status': 'DRIFT', 'findings': ['site.json unreadable: %s' % e], 'warnings': [], 'layers': {}}
    sh = site.get('shell') if isinstance(site.get('shell'), dict) else None
    f, w, layers = [], [], {}
    local = os.path.join(room, 'factory.js')
    local_sha = sha256(local) if os.path.isfile(local) else None
    if sh is None:
        f.append('no site.json "shell" block (legacy per-room copy, undeclared)')
        if local_sha:
            hit = [v for v, m in mans.items() if m['files']['factory.js']['sha256'] == local_sha]
            f.append('local factory.js sha256 %s = %s' % (local_sha[:8], hit[0] if hit else 'no pinned release'))
        return {'room': name, 'status': 'DRIFT', 'findings': f, 'warnings': w, 'layers': layers, 'localSha': local_sha}
    base = sh.get('base')
    man = mans.get(base)
    if not man:
        f.append('shell.base %r has no shell/%s/SHELL.json' % (base, base))
    fork = bool(sh.get('fork'))
    fork_file = posixpath.normpath(sh.get('file', 'factory.js')) if fork else None
    ov = sh.get('overrides') or {}

    def pinned_entries(kind, items):
        out = {}
        for e in items or []:
            if not isinstance(e, dict) or not e.get('file'):
                f.append('%s entry %r must be {file, sha256, reason}' % (kind, e))
                continue
            fn = posixpath.normpath(e['file'])
            p = os.path.join(room, fn)
            if not os.path.isfile(p):
                f.append('%s %s declared but missing' % (kind, fn))
            elif not e.get('sha256'):
                f.append('%s %s has no sha256 pin' % (kind, fn))
            elif e['sha256'] != sha256(p):
                f.append('%s %s sha256 differs from declaration' % (kind, fn))
            if not e.get('reason'):
                f.append('%s %s has no reason' % (kind, fn))
            out[fn] = e
        return out

    modules = pinned_entries('module', ov.get('modules'))
    keep = pinned_entries('keep', sh.get('keep'))
    layers['modules'] = sorted(modules)
    layers['keep'] = sorted(keep)
    for layer in ('theme', 'copy', 'legal'):
        items = ov.get(layer) or []
        layers[layer] = items
        for it in items:
            path = it.split(':', 1)[0].split('#', 1)[0]
            if path and not os.path.exists(os.path.join(room, path)):
                f.append('%s override %s missing' % (layer, it))
    inline_decl = {}
    for e in ov.get('inline') or []:
        if not isinstance(e, dict) or not e.get('page') or not e.get('sha256') or not e.get('reason'):
            f.append('inline entry %r must be {page, sha256, reason}' % (e,))
            continue
        inline_decl[(e['page'], e['sha256'])] = e
    used_inline = set()
    layers['inline'] = len(inline_decl)
    layers['fork'] = fork

    shell_tags, loaded_local = [], set()
    for s in scripts(room):
        a, page, where = s['attrs'], s['page'], '%s:%d' % (s['page'], s['line'])
        src = a.get('src')
        if src is None:
            typ = (a.get('type') or '').strip().lower()
            if typ in DATA_TYPES:
                continue
            text = s['text']
            if not text.strip():
                continue
            h = sha256b(text.encode('utf-8'))
            decl = inline_decl.get((page, h))
            if decl is None:
                f.append('%s undeclared inline <script> (sha256 %s)' % (where, h[:12]))
                f.extend(injection_findings(text, where + ' inline', False))
            else:
                used_inline.add((page, h))
                f.extend(injection_findings(text, where + ' inline', bool(decl.get('injects'))))
            continue
        src = src.strip()
        if FIREBASE_RE.match(src):
            continue
        em = EMOJI_RE.match(src)
        if em:
            if not EXACT_VER.match(em.group(1)) or not a.get('integrity'):
                w.append('%s emoji-picker-element@%s has no SRI pin (mutable range / no integrity)' % (where, em.group(1)))
            continue
        m = PIN_RE.match(src)
        pre = PRE_RE.match(src)
        if m or (pre and man and pre.group(1) == man.get('sourceCommit')):
            ver, fn = (m.group(2), m.group(3)) if m else (base, pre.group(2))
            shell_tags.append((page, fn))
            if ver != base:
                f.append('%s loads shell %s but shell.base is %s' % (where, ver, base))
            elif man and man['files'].get(fn, {}).get('integrity') != a.get('integrity'):
                f.append('%s %s: integrity missing or not the SHELL.json value' % (where, fn))
            if a.get('crossorigin') != 'anonymous':
                f.append('%s %s: crossorigin="anonymous" required for SRI' % (where, fn))
            continue
        if re.match(r'^(?:[a-z][a-z0-9+.-]*:|//)', src, re.I):
            f.append('%s loads undeclared remote script %s' % (where, src))
            continue
        rel = local_ref(page, src)
        if rel is None:
            f.append('%s loads a script outside the room: %s' % (where, src))
            continue
        loaded_local.add(rel)
        if fork and rel == fork_file:
            shell_tags.append((page, 'factory.js'))
        elif rel in modules or rel in keep:
            pass
        elif posixpath.basename(rel) in SHELL_FILES:
            f.append('%s loads local %s (not a declared fork)' % (where, rel))
        else:
            f.append('%s loads undeclared local script %s' % (where, rel))
        if not os.path.isfile(os.path.join(room, rel)):
            f.append('%s loads %s, which does not exist' % (where, rel))

    for key in sorted(set(inline_decl) - used_inline):
        f.append('inline declaration for %s (sha256 %s) matches no script' % (key[0], key[1][:12]))

    # runtime injection inside loaded local JS (modules, keep files, anything else loaded)
    for rel in sorted(loaded_local):
        if fork and rel == fork_file:
            continue
        p = os.path.join(room, rel)
        if os.path.isfile(p):
            decl = modules.get(rel) or keep.get(rel) or {}
            f.extend(injection_findings(open(p, encoding='utf-8', errors='replace').read(), rel, bool(decl.get('injects'))))

    # any local shell copy anywhere in the room that is not the declared fork
    hashes = shell_hashes(mans)
    for p in walk(room, ('.js', '.mjs')):
        rel = os.path.relpath(p, room).replace(os.sep, '/')
        if fork and rel == fork_file:
            continue
        data = open(p, 'rb').read()
        if sha256b(data) in hashes or SHELL_HEADER_RE.search(data[:600].decode('utf-8', 'replace')):
            f.append('%s is a shell copy (release hash or SubX factory header) and is not the declared fork%s'
                     % (rel, '' if rel != 'factory.js' or fork else '; stale local factory.js, delete it'))

    if fork:
        for k in ('reason', 'sha256'):
            if not sh.get(k):
                f.append('fork without shell.%s' % k)
        if not sh.get('exception'):
            f.append('fork without shell.exception (EXCEPTIONS.md row)')
        p = os.path.join(room, fork_file)
        if not os.path.isfile(p):
            f.append('fork file %s missing' % fork_file)
        else:
            got = sha256(p)
            if got != sh.get('sha256'):
                f.append('fork file sha256 %s != declared %s (undeclared edit)' % (got[:8], str(sh.get('sha256'))[:8]))
            if man:
                layers['forkDiffLines'] = diff_lines(os.path.join(man['_dir'], 'factory.js'), p)
        if not any(fn == 'factory.js' for _, fn in shell_tags):
            f.append('no page loads the fork file %s (no shell runs)' % fork_file)
    else:
        if not any(fn == 'factory.js' for _, fn in shell_tags):
            f.append('no pinned factory.js <script> on any page (no shell runs)')
    f = list(dict.fromkeys(f))
    status = 'DRIFT' if f else ('FORK' if fork else ('WARN' if w else 'OK'))
    return {'room': name, 'status': status, 'base': base, 'findings': f, 'warnings': w,
            'layers': layers, 'localSha': local_sha}


def suggest(room):
    """Print the inline/keep sha256 entries a room PR would declare (helper; not a check)."""
    out = {'inline': [], 'scripts': []}
    for s in scripts(room):
        if s['attrs'].get('src') is None and (s['attrs'].get('type') or '').lower() not in DATA_TYPES and s['text'].strip():
            out['inline'].append({'page': s['page'], 'sha256': sha256b(s['text'].encode('utf-8')), 'reason': 'TODO'})
        elif s['attrs'].get('src') and not re.match(r'^(?:[a-z][a-z0-9+.-]*:|//)', s['attrs']['src'], re.I):
            rel = local_ref(s['page'], s['attrs']['src'])
            if rel and os.path.isfile(os.path.join(room, rel)):
                out['scripts'].append({'file': rel, 'sha256': sha256(os.path.join(room, rel)), 'reason': 'TODO'})
    out['scripts'] = list({e['file']: e for e in out['scripts']}.values())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rooms', nargs='+')
    ap.add_argument('--shell-root', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shell'))
    ap.add_argument('--json')
    ap.add_argument('--md')
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--suggest', action='store_true')
    a = ap.parse_args()
    if a.suggest:
        print(json.dumps({os.path.basename(os.path.normpath(r)): suggest(r) for r in a.rooms}, indent=2))
        return
    mans = manifests(a.shell_root)
    res = [check(r, mans) for r in a.rooms]
    lines = ['| Room | Status | Base | Declared layers | Findings | Warnings |', '|---|---|---|---|---|---|']
    for r in res:
        lay = ', '.join('%s=%s' % (k, v) for k, v in r['layers'].items() if v) or '-'
        lines.append('| %s | %s | %s | %s | %s | %s |' % (r['room'], r['status'], r.get('base') or '-', lay,
                     '; '.join(r['findings']) or '-', '; '.join(r['warnings']) or '-'))
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
