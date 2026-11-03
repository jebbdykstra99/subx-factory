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
  - a pin counts only if it will run: classic type (empty/JS; type=module is DRIFT since currentScript is null), no
    nomodule, no query/fragment on the URL, not inside <template>, <noscript>, raw-text or foreign (svg/math, so
    also <foreignObject>) elements, no duplicated attributes, and not blocked by a CSP (meta tag, or a header rule in
    _headers / firebase.json / netlify.toml / vercel.json); other header CSP is left to the C4 preview
  - index.html must run a pin, and so must every page that runs room JS (local scripts, the Firebase SDK, declared
    inline code) unless it is listed in shell.noShell; a noShell page may load only keep files (noShellOk ones once
    any keep entry uses the flag) and declared inline code: modules, Firebase, remote scripts and frames are DRIFT
  - a meta CSP after the pin or in <body> is treated as applying (conservative); a hash-only CSP must list every
    integrity hash on the pin
  - SVG <script href|xlink:href> is a script source; <meta http-equiv=refresh> to javascript:/data: or an undeclared
    remote URL is DRIFT (declared in overrides.refresh = WARN); remote modulepreload and CSS @import are WARN
  - static import / export-from in inline or local JS: remote specifiers must be listed in the declaring entry's
    "imports"; local ones must themselves be declared modules/keep files (scanned transitively)
  - C14 redirect stubs: a page whose only code is ONE classic inline <script> equal to the nest_stubs.py template
    (only the slug literal may differ) or a bare location.replace('/<same-origin path>'), with no other scripts, no
    on*= handlers or javascript: URLs, no frames, no forms, no <base href>, no remote script preloads and no meta
    refresh off the origin, is a redirect stub: it needs neither shell.noShell nor a per-page inline sha256. Pages
    listed in shell.redirects (or carrying the nest_stubs.py marker) that fail this test are DRIFT with the reason
  - C15 noShell inline limits: on a noShell page, declared inline code may not carry "injects" or remote "imports",
    and inline code naming a Firebase SDK URL (gstatic.com/firebasejs, /__/firebase/, an npm CDN firebase package)
    counts as loading the Firebase SDK
  - Comment ends: browsers end a comment at <!-->, <!---> and --!>, which some Python html.parser versions do not.
    Any of the three anywhere in a page is DRIFT (independent of the Python version), so markup hidden behind one
    can never be skipped by the checker while a browser runs it
  - URL normalization: every src, href, import specifier and refresh URL is read the way a browser reads it
    before the local/remote decision (entities decoded once by the parser, leading/trailing C0 controls and spaces
    stripped, tab/CR/LF removed anywhere, \\ read as /, %2e read as . for local paths). Anything that then starts
    with // or a scheme is remote
Runtime injection detection is BEST-EFFORT static analysis: createElement('script') or a non-literal createElement,
import(), importScripts, document.write('<script'), eval, new Function, Worker/SharedWorker, serviceWorker.register.
Each is DRIFT unless the declaring entry carries "injects": "<reason>"; one that names a factory/shell file is always
DRIFT. Obfuscated code can evade this, so every declared module/keep file still needs human review; its sha256 pins
the reviewed bytes. Any local .js that is a shell copy (release hash or SubX factory header) and is not the declared
fork is DRIFT.

Never writes to the room, Firestore, or the network. Exit 1 with --strict when any room has DRIFT.
"""
import argparse, glob, hashlib, json, os, posixpath, re, subprocess, sys
from urllib.parse import unquote
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
# C15: a Firebase SDK URL anywhere in inline code (static or dynamic import, importScripts, injected src)
FIREBASE_SDK_RE = re.compile(r'gstatic\.com/firebasejs/|/__/firebase/|(?:cdn\.jsdelivr\.net/npm|unpkg\.com|esm\.sh|esm\.run'
                             r'|cdn\.skypack\.dev|ga\.jspm\.io/npm:|cdnjs\.cloudflare\.com/ajax/libs)/@?firebase\b', re.I)
# Comment ends the HTML spec honours but Python's html.parser may not (abrupt <!--> / <!--->, and --!>)
COMMENT_TRAP_RE = re.compile(r'<!--->|<!-->|--!>')
# C14: the one inline <script> nest_stubs.py writes into every nest page; only {slug} may differ
NEST_MARK = 'subx-nest-stub: generated by nest_stubs.py'
NEST_SLUG = r'[a-z0-9]+(?:-[a-z0-9]+)*'
NEST_TEMPLATE = (
    "\n    (function () {\n"
    "      var path = location.pathname || '/{slug}';\n"
    "      if (path.charAt(0) !== '/') path = '/' + path;\n"
    "      path = path.replace(/\\.html$/, '');\n"
    "      try { sessionStorage.setItem('subx.restorePath', path + (location.search || '') + (location.hash || '')); } catch (e) {}\n"
    "      location.replace('/' + (location.search || '') + (location.hash || ''));\n"
    "    })();\n  ")
NEST_RE = re.compile('^' + re.escape(NEST_TEMPLATE).replace(re.escape('{slug}'), NEST_SLUG) + '$')
# a bare same-origin bounce: location.replace('/...') with a literal path that cannot leave the origin
# (no //, no /\, no whitespace or escapes, which browsers strip or reinterpret)
BARE_RE = re.compile(r'''^\s*(?:window\.)?location\.replace\(\s*(['"])(/(?![/\\])[A-Za-z0-9._~!$&()*+,;=:@%/?#-]*)\1\s*\)\s*;?\s*$''')


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
        self.metas, self.links, self.styles, self._style = [], [], [], None
        self.forms, self.comments, self.comment_traps = [], [], []
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
            # SVG <script> loads its source from href / xlink:href, not src (C7)
            if 'src' not in a and (self._ctx['svg'] or self._ctx['math']):
                for k in ('href', 'xlink:href'):
                    if a.get(k) is not None:
                        a['src'] = a[k]
                        break
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
        if tag == 'meta' and a.get('http-equiv'):
            self.metas.append({'line': line, 'equiv': a['http-equiv'].strip().lower(), 'content': a.get('content') or ''})
        if tag == 'link':
            self.links.append({'line': line, 'attrs': a})
        if tag == 'style' and not closed:
            self._style = {'line': line, 'text': []}
        if tag == 'form' or 'formaction' in a:
            self.forms.append({'line': line, 'tag': tag})
        if tag in ('iframe', 'frame', 'object', 'embed'):
            self.frames.append({'line': line, 'tag': tag, 'attrs': a, 'dup': dup})
        if tag in self._ctx and not closed:
            self._ctx[tag] += 1

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, True)

    def handle_comment(self, data):
        self.comments.append(data)

    def handle_data(self, data):
        if self._cur is not None:
            self._cur['text'].append(data)
        elif self._style is not None:
            self._style['text'].append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self._cur is not None:
            self._cur['text'] = ''.join(self._cur['text'])
            self.out.append(self._cur)
            self._cur = None
        elif tag == 'style' and self._style is not None:
            self._style['text'] = ''.join(self._style['text'])
            self.styles.append(self._style)
            self._style = None
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
        raw = open(page, encoding='utf-8', errors='replace').read()
        # browsers end a comment at <!-->, <!---> or --!>; flag them on the raw bytes so no parser version can hide markup
        p.comment_traps = [(raw.count('\n', 0, m.start()) + 1, m.group(0)) for m in COMMENT_TRAP_RE.finditer(raw)]
        p.feed(raw)
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


def norm_url(u):
    """A URL as the browser's URL parser sees it (attribute entities are already decoded once by the parser): strip
    leading/trailing C0 controls and spaces, drop tab/CR/LF anywhere, read \\ as / (http(s) pages)."""
    u = re.sub(r'^[\x00-\x20]+|[\x00-\x20]+$', '', u or '')
    return re.sub(r'[\t\n\r]', '', u).replace('\\', '/')


def local_ref(base_file, src):
    """Room-relative posix path for a local src (relative to base_file), or None if it escapes the room."""
    clean = unquote(norm_url(src).split('#', 1)[0].split('?', 1)[0])
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


# ---- CSP (F2): does a policy let the pinned <script> load? ----
PIN_HOST, PIN_PATH = 'cdn.jsdelivr.net', '/gh/jebbdykstra99/subx-factory@'
HOST_SRC_RE = re.compile(r'^(?:([a-z][a-z0-9+.-]*)://)?(\*|\*\.[^/:]+|[^/:*]+)(?::(\d+|\*))?(/.*)?$', re.I)


def csp_policies(text):
    """A Content-Security-Policy value -> list of policies, each {directive: [sources]} (comma = several policies)."""
    out = []
    for pol in (text or '').split(','):
        d = {}
        for part in pol.split(';'):
            toks = part.split()
            if toks and toks[0].lower() not in d:  # first occurrence of a directive wins
                d[toks[0].lower()] = toks[1:]
        if d:
            out.append(d)
    return out


def csp_allows_pin(policy, url, integrity, nonce):
    """True if this one policy lets <script src=url integrity=... nonce=...> load. Directive order for a script
    element: script-src-elem, script-src, default-src; no such directive = allowed."""
    srcs = next((policy[k] for k in ('script-src-elem', 'script-src', 'default-src') if k in policy), None)
    if srcs is None:
        return True
    low = [x.lower() for x in srcs]
    toks = [t.split('?', 1)[0] for t in (integrity or '').split() if re.match(r'^sha(?:256|384|512)-', t)]
    if toks and all("'%s'" % t in srcs for t in toks):  # CSP3: every integrity hash must be listed
        return True
    if nonce and "'nonce-%s'" % nonce in srcs:
        return True
    if "'strict-dynamic'" in low:  # host and scheme sources are ignored
        return False
    path = url.split('://', 1)[1].split('/', 1)
    upath = '/' + (path[1] if len(path) > 1 else '')
    for x in low:
        if x in ('*', 'https:', 'http:'):
            return True
        if x.startswith("'"):
            continue
        m = HOST_SRC_RE.match(x)
        if not m:
            continue
        scheme, host, port, p = m.groups()
        if scheme not in (None, 'https', 'http'):
            continue
        if not (host == PIN_HOST or host == '*' or (host.startswith('*.') and PIN_HOST.endswith(host[1:]))):
            continue
        if port not in (None, '443', '*'):
            continue
        if p and not (upath.startswith(p) if p.endswith('/') else upath == p):
            continue
        return True
    return False


def _pat_re(pat, kind):
    """Header-rule path pattern -> regex. kind: 'splat' (_headers / netlify.toml), 'glob' (firebase), 'ptr' (vercel)."""
    pat = re.sub(r'^https?://[^/]+', '', pat.strip()) or '/'
    out, i = '', 0
    while i < len(pat):
        c = pat[i]
        if kind == 'glob' and pat.startswith('**', i):
            out += '.*'; i += 2; continue
        if c == '*':
            out += '.*' if kind != 'glob' else '[^/]*'
        elif kind == 'glob' and c == '?':
            out += '[^/]'
        elif kind == 'glob' and c == '{':
            j = pat.find('}', i)
            if j < 0:
                return None
            out += '(?:%s)' % '|'.join(re.escape(x) for x in pat[i + 1:j].split(',')); i = j + 1; continue
        elif kind == 'ptr' and c == '(':
            depth, j = 0, i
            while j < len(pat):
                depth += {'(': 1, ')': -1}.get(pat[j], 0)
                if depth == 0:
                    break
                j += 1
            out += pat[i:j + 1]; i = j + 1; continue
        elif c == ':' and kind != 'glob' and re.match(r'[A-Za-z_]', pat[i + 1:i + 2]):
            m = re.match(r':[A-Za-z_]\w*([*+?])?', pat[i:])
            out += '.*' if m.group(1) in ('*', '+') else '[^/]+'
            i += len(m.group(0)); continue
        else:
            out += re.escape(c)
        i += 1
    try:
        return re.compile('^%s$' % out)
    except re.error:
        return None


def header_csps(room):
    """Header CSP rules from hosting config: [(file, pattern, compiled-or-None, value)], plus parse warnings."""
    rules, warns = [], []
    p = os.path.join(room, '_headers')
    if os.path.isfile(p):
        pat = None
        for line in open(p, encoding='utf-8', errors='replace').read().splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            if not line[:1].isspace():
                pat = line.strip()
                continue
            k, _, v = line.strip().partition(':')
            if pat and k.strip().lower() == 'content-security-policy':
                rules.append(('_headers', pat, _pat_re(pat, 'splat'), v.strip()))
    p = os.path.join(room, 'firebase.json')
    if os.path.isfile(p):
        try:
            h = json.load(open(p)).get('hosting') or []
            for site in (h if isinstance(h, list) else [h]):
                for e in site.get('headers') or []:
                    for kv in e.get('headers') or []:
                        if str(kv.get('key', '')).lower() == 'content-security-policy':
                            if e.get('regex'):
                                try:
                                    rx = re.compile(e['regex'])
                                except re.error:
                                    rx = None
                                rules.append(('firebase.json', e['regex'], rx, kv.get('value', '')))
                            else:
                                src = e.get('source', '**')
                                rules.append(('firebase.json', src, _pat_re(src if src.startswith('/') else '/' + src, 'glob'), kv.get('value', '')))
        except Exception as ex:
            warns.append('firebase.json unreadable (%s): its header CSP is not checked; covered only by the C4 preview' % ex)
    p = os.path.join(room, 'netlify.toml')
    if os.path.isfile(p):
        try:
            import tomllib
            for e in tomllib.load(open(p, 'rb')).get('headers') or []:
                for k, v in (e.get('values') or {}).items():
                    if k.lower() == 'content-security-policy':
                        rules.append(('netlify.toml', e.get('for', '/*'), _pat_re(e.get('for', '/*'), 'splat'), v))
        except Exception as ex:
            warns.append('netlify.toml unreadable (%s): its header CSP is not checked; covered only by the C4 preview' % ex)
    p = os.path.join(room, 'vercel.json')
    if os.path.isfile(p):
        try:
            for e in json.load(open(p)).get('headers') or []:
                for kv in e.get('headers') or []:
                    if str(kv.get('key', '')).lower() == 'content-security-policy':
                        rules.append(('vercel.json', e.get('source', '/(.*)'), _pat_re(e.get('source', '/(.*)'), 'ptr'), kv.get('value', '')))
        except Exception as ex:
            warns.append('vercel.json unreadable (%s): its header CSP is not checked; covered only by the C4 preview' % ex)
    return rules, warns


def page_urls(page):
    """URL paths a page is served at (for header rule matching): /a.html, /a, and / or /dir/ for index.html."""
    u = ['/' + page]
    if page.endswith('.html'):
        u.append('/' + page[:-5])
    if posixpath.basename(page) == 'index.html':
        d = posixpath.dirname(page)
        u.append('/' + (d + '/' if d else ''))
    return u


def refresh_url(content):
    m = re.match(r'^\s*[\d.]*\s*[;,]?\s*(?:url\s*=\s*)?(.*)$', content or '', re.I | re.S)
    u = (m.group(1) if m else '').strip()
    if u[:1] in '\'"' and u:
        u = u[1:].split(u[0], 1)[0]
    return u.strip()


CSS_IMPORT_RE = re.compile(r"""@import\s+(?:url\(\s*)?['"]?([^'")\s;]+)""", re.I)
CSS_JSURL_RE = re.compile(r"""url\(\s*['"]?\s*javascript:""", re.I)


def css_notes(text):
    out = []
    for m in CSS_IMPORT_RE.finditer(text):
        if REMOTE_RE.match(norm_url(m.group(1))) and not m.group(1).lower().startswith('data:'):
            out.append('CSS @import of remote %s' % m.group(1))
    if CSS_JSURL_RE.search(text):
        out.append('CSS url(javascript:...) (inert in current browsers)')
    return out


def redirect_stub(pg):
    """C14: (True, kind) if the parsed page is a same-origin redirect stub, else (False, why not)."""
    if pg.comment_traps:
        return False, 'it has a comment end (%s) that browsers and the checker read differently' % pg.comment_traps[0][1]
    if pg.code:
        return False, 'it has on*= handlers or javascript: URLs'
    if pg.frames:
        return False, 'it has frames (iframe/frame/object/embed)'
    if pg.forms:
        return False, 'it has a form'
    if any(b_['attrs'].get('href') is not None for b_ in pg.bases):
        return False, 'it has <base href>'
    for ln in pg.links:
        rel_ = (ln['attrs'].get('rel') or '').lower().split()
        if 'modulepreload' in rel_ or 'import' in rel_ or ('preload' in rel_ and (ln['attrs'].get('as') or '').lower() in ('script', 'worker')):
            return False, 'it preloads a script'
    for mt in pg.metas:
        if mt['equiv'] == 'refresh':
            u = re.sub(r'[\x00-\x20]', '', norm_url(refresh_url(mt['content'])))
            if u and not (u.startswith('/') and not u.startswith('//')) and not u.startswith(('#', '?')):
                return False, 'its meta refresh does not stay on the origin'
    code = [s for s in pg.out if (s['attrs'].get('type') or '').strip().lower() not in DATA_TYPES
            and (s['attrs'].get('src') is not None or s['text'].strip())]
    if len(code) != 1:
        return False, 'it has %d scripts (a stub has exactly one inline script)' % len(code)
    s = code[0]
    if s['attrs'].get('src') is not None:
        return False, 'its script is external'
    if (s['attrs'].get('type') or '').strip().lower() not in ('', 'text/javascript') or s['inert'] or s['dup']:
        return False, 'its script is not a plain classic inline script'
    text = s['text'].replace('\r\n', '\n')
    if NEST_RE.match(text):
        return True, 'nest stub'
    if BARE_RE.match(text):
        return True, 'bare same-origin location.replace'
    return False, 'its inline script is neither the nest_stubs.py template (slug only) nor a bare same-origin location.replace'


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
            if re.search(r'[\x00-\x20\\%]', e['file']):
                f.append('%s entry %r has a space, control character, backslash or %% in its path: a browser never requests '
                         'that literal path' % (kind, e['file']))
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
    refresh_decl = {}
    for e in ov.get('refresh') or []:
        if not isinstance(e, dict) or not e.get('page') or not e.get('url') or not e.get('reason'):
            f.append('refresh entry %r must be {page, url, reason}' % (e,))
            continue
        refresh_decl[(e['page'], e['url'])] = e
    no_shell = sh.get('noShell') or []
    if not isinstance(no_shell, list) or not all(isinstance(x, str) for x in no_shell):
        f.append('shell.noShell must be a list of page paths')
        no_shell = []
    no_shell = {posixpath.normpath(x.lstrip('/')) for x in no_shell}
    for x in sorted(no_shell):
        if x == 'index.html':
            f.append('shell.noShell lists index.html: the main page must run the shell')
        elif not os.path.isfile(os.path.join(room, x)):
            f.append('shell.noShell page %s does not exist' % x)
    layers['noShell'] = sorted(no_shell)
    redirects = sh.get('redirects') or []
    if not isinstance(redirects, list) or not all(isinstance(x, str) for x in redirects):
        f.append('shell.redirects must be a list of page paths')
        redirects = []
    redirects = {posixpath.normpath(x.lstrip('/')) for x in redirects}
    for x in sorted(redirects):
        if x == 'index.html':
            f.append('shell.redirects lists index.html: the main page must run the shell')
        elif not os.path.isfile(os.path.join(room, x)):
            f.append('shell.redirects page %s does not exist' % x)
    stubs = []
    # C11: once any keep entry sets noShellOk, only flagged keep files may load on noShell pages
    ns_flag = any(isinstance(e, dict) and 'noShellOk' in e for e in (sh.get('keep') or []))
    hdr_rules, hdr_warn = header_csps(room)
    w.extend(hdr_warn)
    used_inline, used_frames, used_refresh = set(), set(), set()
    layers['inline'] = len(inline_decl)
    layers['frames'] = len(frame_decl)
    layers['fork'] = fork

    shell_tags, loaded_local = [], {}
    running, needs = set(), {}  # pages with a running factory.js / fork tag; pages running room JS -> first such item
    ns_items = {}  # page -> [(where, what, allowed)] for the C11 noShell restriction
    ns_keep = {}   # keep file -> first noShell page loading it

    def ns_add(page, where, what, ok):
        ns_items.setdefault(page, []).append((where, what, ok))
    inline_js = []  # (where, text, decl) for import scanning

    ns_decl = []  # C15: (page, where, declaration) for every declared inline code block

    def code_block(page, where, text, kind):
        h = sha256b(text.encode('utf-8'))
        decl = inline_decl.get((page, h))
        if decl is None:
            f.append('%s undeclared %s (sha256 %s)' % (where, kind, h[:12]))
            f.extend(injection_findings(text, where + ' ' + kind, False))
            decl = {}
        else:
            used_inline.add((page, h))
            ns_decl.append((page, where, decl))
            f.extend(injection_findings(text, where + ' ' + kind, bool(decl.get('injects'))))
        fb = FIREBASE_SDK_RE.search(text)
        if fb:  # C15: a Firebase-host import (static or dynamic) loads the Firebase SDK
            needs.setdefault(page, 'Firebase SDK')
            ns_add(page, where, 'Firebase SDK (%s names %s)' % (kind, fb.group(0)), False)
        return decl

    all_pages = []
    for page, pg in pages(room):
        all_pages.append(page)
        is_stub, stub_why = redirect_stub(pg)
        if is_stub:
            stubs.append(page)
        elif page in redirects:
            f.append('%s is listed in shell.redirects but is not a redirect stub: %s' % (page, stub_why))
        elif any(NEST_MARK in c for c in pg.comments):
            f.append('%s carries the nest_stubs.py marker but is not a redirect stub: %s' % (page, stub_why))
        for ln_, tok in pg.comment_traps:
            f.append('%s:%d has %s: browsers end a comment there, so markup after it runs (rewrite the comment as <!-- ... -->)'
                     % (page, ln_, tok))
        # F2: every CSP that applies to the page (meta tags + hosting header rules) must allow the pin
        csp = []
        for mt in pg.metas:
            if mt['equiv'] == 'content-security-policy':
                csp += [('%s:%d <meta> CSP' % (page, mt['line']), pol) for pol in csp_policies(mt['content'])]
        for fn_, pat, rx, val in hdr_rules:
            if rx is None or any(rx.match(u) for u in page_urls(page)):
                csp += [('%s header CSP for %s' % (fn_, pat), pol) for pol in csp_policies(val)]
        # C8: meta refresh navigates the room away
        for mt in pg.metas:
            if mt['equiv'] != 'refresh':
                continue
            raw_u, where = refresh_url(mt['content']), '%s:%d' % (page, mt['line'])
            u = norm_url(raw_u)
            if not u:
                continue
            if _jsurl(u) or re.match(r'^(?:data|blob|vbscript|filesystem):', re.sub(r'[\x00-\x20]', '', u), re.I):
                f.append('%s <meta http-equiv=refresh> to a %s URL' % (where, u.split(':', 1)[0].lower()))
            elif REMOTE_RE.match(u):
                key = (page, u) if (page, u) in refresh_decl else (page, raw_u)
                if key in refresh_decl:
                    used_refresh.add(key)
                    w.append('%s <meta http-equiv=refresh> to remote %s (declared)' % (where, u))
                else:
                    f.append('%s undeclared <meta http-equiv=refresh> to remote %s (declare it in overrides.refresh)' % (where, u))
        # C8: remote modulepreload / preload-as-script / HTML import (no code runs from these alone)
        for ln in pg.links:
            rel_ = (ln['attrs'].get('rel') or '').lower().split()
            href = norm_url(ln['attrs'].get('href'))
            if href and REMOTE_RE.match(href) and ('modulepreload' in rel_ or 'import' in rel_ or
                                                    ('preload' in rel_ and (ln['attrs'].get('as') or '').lower() in ('script', 'worker'))):
                w.append('%s:%d remote <link rel=%s href=%s>' % (page, ln['line'], ' '.join(rel_), href))
        for st in pg.styles:
            for wmsg in css_notes(st['text']):
                w.append('%s:%d <style> %s' % (page, st['line'], wmsg))
        for b in pg.bases:
            if b['attrs'].get('href') is not None:
                f.append('%s:%d <base href=%r> retargets every relative src (not allowed)' % (page, b['line'], b['attrs']['href']))
        for c in pg.code:
            code_block(page, '%s:%d' % (page, c['line']), c['text'], c['kind'])
            needs.setdefault(page, c['kind'])  # C12: declared inline code is room JS
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
                ns_add(page, where, '<%s srcdoc>' % tag, False)
                continue
            src = norm_url((a.get('src') if tag in ('iframe', 'frame', 'embed') else a.get('data')) or '')
            if tag in ('object', 'embed'):
                ns_add(page, where, '<%s>' % tag, False)
                if (page, src) in frame_decl:
                    used_frames.add((page, src))
                else:
                    f.append('%s undeclared <%s> %s' % (where, tag, src or '(no source)'))
                continue
            if not src or src == 'about:blank':
                continue
            ns_add(page, where, '<%s src=%s>' % (tag, src[:60]), False)
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
                if is_stub:  # C14: same-origin redirect stub; a matching declaration is accepted but not required
                    h = sha256b(s['text'].encode('utf-8'))
                    if (page, h) in inline_decl:
                        used_inline.add((page, h))
                    continue
                decl = code_block(page, where, s['text'], 'inline <script>')
                inline_js.append((where + ' inline', s['text'], decl))
                needs.setdefault(page, 'inline <script>')  # C12
                continue
            src = norm_url(src)
            runs = typ in JS_TYPES and 'nomodule' not in a and not s['inert'] and not s['dup']
            if FIREBASE_RE.match(src):
                needs.setdefault(page, 'Firebase SDK')  # C12
                ns_add(page, where, 'Firebase SDK', False)
                continue
            em = EMOJI_RE.match(src)
            if em:
                ns_add(page, where, 'remote script %s' % src, False)
                if not EXACT_VER.match(em.group(1)) or not a.get('integrity'):
                    w.append('%s emoji-picker-element@%s has no SRI pin (mutable range / no integrity)' % (where, em.group(1)))
                continue
            bare = re.split(r'[?#]', src, maxsplit=1)[0]
            if bare != src and (PIN_RE.match(bare) or PRE_RE.match(bare)):
                f.append('%s pin URL carries a query or fragment (%s): pins must be the bare pinned URL, no ?v=' % (where, src[len(bare):][:40]))
                continue
            m = PIN_RE.match(src)
            pre = PRE_RE.match(src)
            if m or (pre and man and pre.group(1) == man.get('sourceCommit')):
                ver, fn = (m.group(2), m.group(3)) if m else (base, pre.group(2))
                if typ == 'module':
                    f.append('%s %s pin has type=module: document.currentScript is null there, so the shell ignores data-site '
                             '(and runs deferred); use a classic <script>' % (where, fn))
                    continue
                if not runs:
                    why = ([('type=%s' % typ)] if typ not in JS_TYPES else []) + (['nomodule'] if 'nomodule' in a else []) \
                        + (['inside <%s>' % t for t in s['inert']]) + (['duplicated attributes'] if s['dup'] else [])
                    f.append('%s %s pin is inert (%s): it does not run' % (where, fn, ', '.join(why)))
                    continue
                blocked = [lbl for lbl, pol in csp if not csp_allows_pin(pol, src, a.get('integrity'), a.get('nonce'))]
                if blocked:
                    f.append('%s %s pin is blocked by %s (script-src/default-src allows neither https://cdn.jsdelivr.net '
                             'nor the pin hash): it does not run' % (where, fn, '; '.join(dict.fromkeys(blocked))))
                    continue
                shell_tags.append((page, fn))
                if fn == 'factory.js':
                    running.add(page)
                if ver != base:
                    f.append('%s loads shell %s but shell.base is %s' % (where, ver, base))
                elif man and man['files'].get(fn, {}).get('integrity') != a.get('integrity'):
                    f.append('%s %s: integrity missing or not the SHELL.json value' % (where, fn))
                if a.get('crossorigin') != 'anonymous':
                    f.append('%s %s: crossorigin="anonymous" required for SRI' % (where, fn))
                continue
            if REMOTE_RE.match(src):
                f.append('%s loads undeclared remote script %s' % (where, src))
                ns_add(page, where, 'remote script %s' % src, False)
                continue
            rel = local_ref(page, src)
            if rel is None:
                f.append('%s loads a script outside the room: %s' % (where, src))
                continue
            loaded_local.setdefault(rel, where)
            if fork and rel == fork_file:
                if runs and typ != 'module':
                    shell_tags.append((page, 'factory.js'))
                    running.add(page)
                else:
                    f.append('%s fork file tag is inert or type=module: it does not run as the shell' % where)
            else:
                needs.setdefault(page, rel)
                if rel in keep and (not ns_flag or keep[rel].get('noShellOk') is True):
                    ns_add(page, where, 'keep file %s' % rel, True)
                    if page in no_shell:
                        ns_keep.setdefault(rel, page)
                else:
                    ns_add(page, where, ('module %s' % rel) if rel in modules else
                           ('keep file %s (not flagged noShellOk)' % rel) if rel in keep else ('script %s' % rel), False)
            if fork and rel == fork_file or rel in modules or rel in keep:
                pass
            elif posixpath.basename(rel) in SHELL_FILES:
                f.append('%s loads local %s (not a declared fork)' % (where, rel))
            else:
                f.append('%s loads undeclared local script %s' % (where, rel))
            if not os.path.isfile(os.path.join(room, rel)):
                f.append('%s loads %s, which does not exist' % (where, rel))

    for key in sorted(set(refresh_decl) - used_refresh):
        f.append('refresh declaration for %s (%s) matches no <meta http-equiv=refresh>' % key)
    for p in walk(room, ('.css',)):
        relc = os.path.relpath(p, room).replace(os.sep, '/')
        for wmsg in css_notes(open(p, encoding='utf-8', errors='replace').read()):
            w.append('%s %s' % (relc, wmsg))
    for key in sorted(set(inline_decl) - used_inline):
        f.append('inline declaration for %s (sha256 %s) matches no script, handler or URL' % (key[0], key[1][:12]))
    for key in sorted(set(frame_decl) - used_frames):
        f.append('frames declaration for %s (%s) matches no frame' % (key[0], key[1][:40]))

    def static_imports(text, where, origin, decl):
        allowed = set(decl.get('imports') or [])
        for spec in import_specs(text):
            raw_spec, spec = spec, norm_url(spec)
            if REMOTE_RE.match(spec) or not spec.startswith(('.', '/')):
                if spec not in allowed and raw_spec not in allowed:
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
        needs.setdefault(q[1].split(':', 1)[0], q[0])
        ns_add(q[1].split(':', 1)[0], q[1], 'module %s (imported by inline code)' % q[0], False)
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
        if rel in ns_keep and import_specs(text):
            f.append('%s is loaded on noShell page %s but imports modules (a noShell page may run only keep files and '
                     'declared inline code)' % (rel, ns_keep[rel]))
        static_imports(text, rel, rel, decl)

    # F1: the main page, and every page that loads room JS (modules, keep files, other local scripts), runs the shell
    if 'index.html' not in all_pages:
        f.append('no index.html: the main page must run the pinned shell')
    elif 'index.html' not in running:
        f.append('index.html runs no shell (no live, running factory.js pin): the main page must run it')
    for pg_ in sorted(needs):
        if pg_ != 'index.html' and pg_ not in running and pg_ not in no_shell:
            f.append('%s loads room JS (%s) but runs no shell; list it in shell.noShell if it is meant to run without the shell'
                     % (pg_, needs[pg_]))
    # C11: a noShell page runs without the kill switch and moderation, so it may load only keep files and inline code
    for pg_ in sorted(no_shell - {'index.html'}):
        if pg_ in running:
            w.append('%s is listed in shell.noShell but runs the shell; remove it from noShell' % pg_)
            continue
        for where, what, ok in ns_items.get(pg_, []):
            if not ok:
                f.append('%s noShell page loads %s: a noShell page may load only keep files%s and declared inline code'
                         % (where, what, ' flagged noShellOk' if ns_flag else ''))
        # C15: declared inline code on a noShell page may not inject code or import remote modules
        for page_, where, decl in ns_decl:
            if page_ != pg_:
                continue
            if decl.get('injects'):
                f.append('%s noShell page declares inline code with "injects" (%s): inline code on a noShell page may not '
                         'inject or evaluate code' % (where, str(decl['injects'])[:40]))
            rem = [x for x in (decl.get('imports') or []) if isinstance(x, str) and (REMOTE_RE.match(norm_url(x)) or not norm_url(x).startswith(('.', '/')))]
            if rem:
                f.append('%s noShell page declares remote "imports" %s: inline code on a noShell page may not import remote modules'
                         % (where, ', '.join(rem)))

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
    layers['redirectStubs'] = len(stubs)
    f = list(dict.fromkeys(f))
    w = list(dict.fromkeys(w))
    status = 'DRIFT' if f else ('FORK' if fork else ('WARN' if w else 'OK'))
    return {'room': name, 'status': status, 'base': base, 'findings': f, 'warnings': w,
            'layers': layers, 'localSha': local_sha}


def suggest(room):
    """Print the inline/frames/keep entries a room PR would declare (helper; not a check)."""
    out = {'inline': [], 'frames': [], 'scripts': [], 'noShell': []}
    for page, pg in pages(room):
        if page != 'index.html' and redirect_stub(pg)[0]:
            continue  # C14: redirect stubs need neither noShell nor an inline hash
        pinned = any(PIN_RE.match(norm_url((s.get('attrs') or {}).get('src'))) for s in pg.out)
        if page != 'index.html' and not pinned and (pg.code or any(
                (s['attrs'].get('src') and (not REMOTE_RE.match(norm_url(s['attrs']['src']))
                                            or FIREBASE_RE.match(norm_url(s['attrs']['src']))))
                or (s['attrs'].get('src') is None and (s['attrs'].get('type') or '').lower() not in DATA_TYPES
                    and s['text'].strip()) for s in pg.out)):
            out['noShell'].append(page)
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
            elif a.get('src') and not REMOTE_RE.match(norm_url(a['src'])):
                rel = local_ref(page, a['src'])
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
