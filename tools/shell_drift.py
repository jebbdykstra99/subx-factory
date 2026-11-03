#!/usr/bin/env python3
"""Shared pinned shell: per-room declaration check (read-only).

  python3 tools/shell_drift.py ROOM_DIR [ROOM_DIR ...] [--shell-root shell] [--json OUT] [--md OUT] [--strict] [--suggest]

A room may differ from the pinned shell only through DECLARED layers in its site.json "shell" block:
  1. config      site.json keys (features, skin, rail, nests, minAge, imageUploads, ...)   always allowed
  2. overrides   theme, copy, legal (files must exist), modules (local JS through documented hooks, sha256-pinned),
                 inline (each executable inline <script>, on*= handler or javascript: URL: sha256 of its exact text, per page),
                 frames (each srcdoc / object / embed / remote iframe, per page)
  3. fork        a full room copy of factory.js pinned to a named base version, with its sha256 and a reason
  keep           room scripts that are not shell code (gate.js, takedown.js ...), each sha256-pinned
Anything else is DRIFT. Status per room: OK, WARN (OK + non-blocking notes), FORK (declared fork), DRIFT.

Pages are parsed with html.parser (quoted, single-quoted and unquoted attributes; comments ignored), and every
page-like file (*.html, *.htm, *.xhtml, *.shtml, *.svg, *.php, *.phtml) under the room is scanned (except .git,
node_modules, dot-dirs). Besides <script>:
  - on*= event handlers and javascript: URLs are code: declared in overrides.inline like inline scripts
  - iframe/frame srcdoc, object, embed are DRIFT unless declared in overrides.frames; a remote iframe/frame src is
    WARN unless declared; data:/blob:/javascript: frame sources are DRIFT
  - <base href> is DRIFT (it retargets every relative src, including declared modules)
  - a pin counts only if it will run: type empty/JS/module, no nomodule, not inside <template>, <noscript>, raw-text
    or foreign (svg/math) elements, and no duplicated attributes on the tag
  - static import / export-from in inline or local JS: remote specifiers must be listed in the declaring entry's
    "imports"; local ones must themselves be declared modules/keep files (scanned transitively)
Runtime injection detection is BEST-EFFORT static analysis: createElement('script') or a non-literal createElement,
import(), importScripts, document.write('<script'), eval, new Function, Worker/SharedWorker, serviceWorker.register.
Each is DRIFT unless the declaring entry carries "injects": "<reason>"; one that names a factory/shell file is always
DRIFT. Obfuscated code can evade this, so every declared module/keep file still needs human review; its sha256 pins
the reviewed bytes. Any local .js that is a shell copy (release hash or SubX factory header) and is not the declared
fork is DRIFT.

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
JS_TYPES = ('', 'text/javascript', 'application/javascript', 'module', 'text/ecmascript', 'application/ecmascript')
# a <script> inside these never runs as a page script (template/noscript content, raw text, foreign content)
INERT_CTX = ('template', 'noscript', 'textarea', 'title', 'xmp', 'noembed', 'noframes', 'iframe', 'svg', 'math', 'plaintext')
PAGE_EXTS = ('.html', '.htm', '.xhtml', '.shtml', '.svg', '.php', '.phtml')
INJECT_RE = re.compile(r"""createElement(?:NS)?\s*\([^)]*?['"`]script['"`]\s*\)|createElement\s*\(\s*[^'"`\s)]|\bimport\s*\("""
                       r"""|\bimportScripts\s*\(|document\s*\.\s*write(?:ln)?\s*\([^)]*<\s*script|\beval\s*\(|[(,=:]\s*eval\s*[),;]|\bnew\s+Function\s*\("""
                       r"""|\bnew\s+(?:Shared)?Worker\s*\(|serviceWorker\s*\.\s*register""", re.I)
# static ES module imports / re-exports: import x from 'spec', import 'spec', export {a} from 'spec'
IMPORT_RE = re.compile(r"""(?:^|[;{}])\s*(?:import|export)\s*(?:[\w*{}\s,$]+?\s*from\s*)?(['"])([^'"\n]+)\1""", re.M)
REMOTE_RE = re.compile(r'^(?:[a-z][a-z0-9+.-]*:|//)', re.I)
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


def _jsurl(v):
    return re.sub(r'[\x00-\x20]', '', v or '').lower().startswith('javascript:')


class _Page(HTMLParser):
    """Collects <script>s (with inert context), event handlers, javascript: URLs, frames and <base>."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out, self.code, self.frames, self.bases, self._cur = [], [], [], [], None
        self._ctx = {t: 0 for t in INERT_CTX}

    def _attrs(self, tag, attrs, line):
        d, dup = {}, []
        for k, v in attrs:
            k = k.lower()
            if k in d:
                dup.append(k)
                continue
            d[k] = v if v is not None else ''
        for k, v in d.items():
            if k.startswith('on'):
                self.code.append({'line': line, 'kind': '<%s %s=>' % (tag, k), 'text': v})
            elif _jsurl(v):
                self.code.append({'line': line, 'kind': '<%s %s=javascript:>' % (tag, k), 'text': v})
        return d, dup

    def _start(self, tag, attrs, closed):
        line = self.getpos()[0]
        a, dup = self._attrs(tag, attrs, line)
        if tag == 'script':
            rec = {'attrs': a, 'dup': dup, 'inert': [t for t in INERT_CTX if self._ctx[t]], 'line': line}
            if closed:
                rec['text'] = ''
                self.out.append(rec)
            else:
                rec['text'] = []
                self._cur = rec
            return
        if tag == 'base':
            self.bases.append({'line': line, 'attrs': a})
        if tag in ('iframe', 'frame', 'object', 'embed'):
            self.frames.append({'line': line, 'tag': tag, 'attrs': a, 'dup': dup})
        if tag in self._ctx and not closed:
            self._ctx[tag] += 1

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, True)

    def handle_data(self, data):
        if self._cur is not None:
            self._cur['text'].append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self._cur is not None:
            self._cur['text'] = ''.join(self._cur['text'])
            self.out.append(self._cur)
            self._cur = None
        elif tag in self._ctx and self._ctx[tag]:
            self._ctx[tag] -= 1


def walk(room, exts):
    for d, dirs, files in os.walk(room):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith('.'))
        for fn in sorted(files):
            if fn.lower().endswith(exts):
                yield os.path.join(d, fn)


def pages(room):
    """(relpath, parsed _Page) for every page-like file. Comments are not markup."""
    for page in walk(room, PAGE_EXTS):
        p = _Page()
        p.feed(open(page, encoding='utf-8', errors='replace').read())
        p.close()
        if p._cur is not None:  # unterminated <script>
            p._cur['text'] = ''.join(p._cur['text'])
            p.out.append(p._cur)
        yield os.path.relpath(page, room).replace(os.sep, '/'), p


def scripts(room):
    """Every <script> in every page: dicts with page, line, attrs, dup, inert, text."""
    out = []
    for rel, p in pages(room):
        for s in p.out:
            s['page'] = rel
            out.append(s)
    return out


def local_ref(base_file, src):
    """Room-relative posix path for a local src (relative to base_file), or None if it escapes the room."""
    clean = src.split('#', 1)[0].split('?', 1)[0]
    if clean.startswith('/'):
        rel = posixpath.normpath(clean.lstrip('/'))
    else:
        rel = posixpath.normpath(posixpath.join(posixpath.dirname(base_file), clean))
    return None if rel.startswith('..') else rel


def injection_findings(text, where, allowed):
    f = []
    for m in INJECT_RE.finditer(text):
        window = text[max(0, m.start() - 200): m.end() + 300]
        if SHELL_REF_RE.search(window):
            f.append('%s injects a script that names a factory/shell file at runtime' % where)
        elif not allowed:
            f.append('%s injects or evaluates code at runtime (%s) without a declared "injects" reason' % (where, m.group(0)[:40]))
    return sorted(set(f))


def import_specs(text):
    return [m.group(2) for m in IMPORT_RE.finditer(text)]


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
    frame_decl = {}
    for e in ov.get('frames') or []:
        key = e.get('src') or e.get('sha256') if isinstance(e, dict) else None
        if not isinstance(e, dict) or not e.get('page') or not key or not e.get('reason'):
            f.append('frames entry %r must be {page, src | sha256 (of srcdoc), reason}' % (e,))
            continue
        frame_decl[(e['page'], key)] = e
    used_inline, used_frames = set(), set()
    layers['inline'] = len(inline_decl)
    layers['frames'] = len(frame_decl)
    layers['fork'] = fork

    shell_tags, loaded_local = [], {}
    inline_js = []  # (where, text, decl) for import scanning

    def code_block(page, where, text, kind):
        h = sha256b(text.encode('utf-8'))
        decl = inline_decl.get((page, h))
        if decl is None:
            f.append('%s undeclared %s (sha256 %s)' % (where, kind, h[:12]))
            f.extend(injection_findings(text, where + ' ' + kind, False))
            decl = {}
        else:
            used_inline.add((page, h))
            f.extend(injection_findings(text, where + ' ' + kind, bool(decl.get('injects'))))
        return decl

    for page, pg in pages(room):
        for b in pg.bases:
            if b['attrs'].get('href') is not None:
                f.append('%s:%d <base href=%r> retargets every relative src (not allowed)' % (page, b['line'], b['attrs']['href']))
        for c in pg.code:
            code_block(page, '%s:%d' % (page, c['line']), c['text'], c['kind'])
        for fr in pg.frames:
            a, where, tag = fr['attrs'], '%s:%d' % (page, fr['line']), fr['tag']
            if fr['dup']:
                f.append('%s <%s> has duplicated attributes %s' % (where, tag, fr['dup']))
            if 'srcdoc' in a:
                h = sha256b(a['srcdoc'].encode('utf-8'))
                if (page, h) in frame_decl:
                    used_frames.add((page, h))
                else:
                    f.append('%s undeclared <%s srcdoc> (sha256 %s)' % (where, tag, h[:12]))
                continue
            src = (a.get('src') if tag in ('iframe', 'frame', 'embed') else a.get('data')) or ''
            src = src.strip()
            if tag in ('object', 'embed'):
                if (page, src) in frame_decl:
                    used_frames.add((page, src))
                else:
                    f.append('%s undeclared <%s> %s' % (where, tag, src or '(no source)'))
                continue
            if not src or src == 'about:blank':
                continue
            if re.match(r'^(?:data|blob|javascript|filesystem):', re.sub(r'[\x00-\x20]', '', src), re.I):
                f.append('%s <%s> with a %s source' % (where, tag, src.split(':', 1)[0].lower()))
            elif REMOTE_RE.match(src):
                if (page, src) in frame_decl:
                    used_frames.add((page, src))
                else:
                    w.append('%s remote <%s src=%s> (declare it in overrides.frames)' % (where, tag, src))
            # local frame pages are scanned as pages in their own right

        for s in pg.out:
            a, where = s['attrs'], '%s:%d' % (page, s['line'])
            typ = (a.get('type') or '').strip().lower()
            if s['dup']:
                f.append('%s <script> has duplicated attributes %s (browsers use the first)' % (where, s['dup']))
            src = a.get('src')
            if src is None:
                if typ in DATA_TYPES or not s['text'].strip():
                    continue
                decl = code_block(page, where, s['text'], 'inline <script>')
                inline_js.append((where + ' inline', s['text'], decl))
                continue
            src = src.strip()
            runs = typ in JS_TYPES and 'nomodule' not in a and not s['inert'] and not s['dup']
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
                if not runs:
                    why = ([('type=%s' % typ)] if typ not in JS_TYPES else []) + (['nomodule'] if 'nomodule' in a else []) \
                        + (['inside <%s>' % t for t in s['inert']]) + (['duplicated attributes'] if s['dup'] else [])
                    f.append('%s %s pin is inert (%s): it does not run' % (where, fn, ', '.join(why)))
                    continue
                shell_tags.append((page, fn))
                if ver != base:
                    f.append('%s loads shell %s but shell.base is %s' % (where, ver, base))
                elif man and man['files'].get(fn, {}).get('integrity') != a.get('integrity'):
                    f.append('%s %s: integrity missing or not the SHELL.json value' % (where, fn))
                if a.get('crossorigin') != 'anonymous':
                    f.append('%s %s: crossorigin="anonymous" required for SRI' % (where, fn))
                continue
            if REMOTE_RE.match(src):
                f.append('%s loads undeclared remote script %s' % (where, src))
                continue
            rel = local_ref(page, src)
            if rel is None:
                f.append('%s loads a script outside the room: %s' % (where, src))
                continue
            loaded_local.setdefault(rel, where)
            if fork and rel == fork_file:
                if runs:
                    shell_tags.append((page, 'factory.js'))
                else:
                    f.append('%s fork file tag is inert: it does not run' % where)
            elif rel in modules or rel in keep:
                pass
            elif posixpath.basename(rel) in SHELL_FILES:
                f.append('%s loads local %s (not a declared fork)' % (where, rel))
            else:
                f.append('%s loads undeclared local script %s' % (where, rel))
            if not os.path.isfile(os.path.join(room, rel)):
                f.append('%s loads %s, which does not exist' % (where, rel))

    for key in sorted(set(inline_decl) - used_inline):
        f.append('inline declaration for %s (sha256 %s) matches no script, handler or URL' % (key[0], key[1][:12]))
    for key in sorted(set(frame_decl) - used_frames):
        f.append('frames declaration for %s (%s) matches no frame' % (key[0], key[1][:40]))

    def static_imports(text, where, origin, decl):
        allowed = set(decl.get('imports') or [])
        for spec in import_specs(text):
            if REMOTE_RE.match(spec) or not spec.startswith(('.', '/')):
                if spec not in allowed:
                    f.append('%s statically imports %s (not in the declaring entry\'s "imports")' % (where, spec))
                if SHELL_REF_RE.search(spec):
                    f.append('%s statically imports a factory/shell file %s' % (where, spec))
                continue
            rel = local_ref(origin, spec)
            if rel is None:
                f.append('%s imports a module outside the room: %s' % (where, spec))
            else:
                queue.append((rel, where))

    # inline module imports resolve against the page
    queue = []
    for where, text, decl in inline_js:
        static_imports(text, where, where.split(':', 1)[0], decl)
    for q in queue:
        if q[0] not in loaded_local and q[0] not in modules and q[0] not in keep:
            f.append('%s imports undeclared local module %s' % (q[1], q[0]))
        loaded_local.setdefault(q[0], q[1])
    queue = [(rel, src) for rel, src in loaded_local.items()]
    seen = set()
    # local JS (loaded or imported, transitively): runtime injection + static imports
    while queue:
        rel, via = queue.pop(0)
        if rel in seen or (fork and rel == fork_file):
            continue
        seen.add(rel)
        if rel not in modules and rel not in keep and rel not in loaded_local:
            f.append('%s imports undeclared local module %s' % (via, rel))
        p = os.path.join(room, rel)
        if not os.path.isfile(p):
            if rel not in loaded_local:
                f.append('%s imports %s, which does not exist' % (via, rel))
            continue
        decl = modules.get(rel) or keep.get(rel) or {}
        text = open(p, encoding='utf-8', errors='replace').read()
        f.extend(injection_findings(text, rel, bool(decl.get('injects'))))
        static_imports(text, rel, rel, decl)

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
    w = list(dict.fromkeys(w))
    status = 'DRIFT' if f else ('FORK' if fork else ('WARN' if w else 'OK'))
    return {'room': name, 'status': status, 'base': base, 'findings': f, 'warnings': w,
            'layers': layers, 'localSha': local_sha}


def suggest(room):
    """Print the inline/frames/keep entries a room PR would declare (helper; not a check)."""
    out = {'inline': [], 'frames': [], 'scripts': []}
    for page, pg in pages(room):
        for c in pg.code:
            out['inline'].append({'page': page, 'sha256': sha256b(c['text'].encode('utf-8')), 'reason': 'TODO ' + c['kind']})
        for fr in pg.frames:
            a = fr['attrs']
            if 'srcdoc' in a:
                out['frames'].append({'page': page, 'sha256': sha256b(a['srcdoc'].encode('utf-8')), 'reason': 'TODO srcdoc'})
            elif a.get('src') or a.get('data'):
                out['frames'].append({'page': page, 'src': (a.get('src') or a.get('data')).strip(), 'reason': 'TODO'})
        for s in pg.out:
            a = s['attrs']
            if a.get('src') is None and (a.get('type') or '').lower() not in DATA_TYPES and s['text'].strip():
                out['inline'].append({'page': page, 'sha256': sha256b(s['text'].encode('utf-8')), 'reason': 'TODO'})
            elif a.get('src') and not REMOTE_RE.match(a['src'].strip()):
                rel = local_ref(page, a['src'].strip())
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
