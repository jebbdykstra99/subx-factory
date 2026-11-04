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
A site.json with mode doorway or parked (topics/site_mode.schema.json) is not a room: its dir must contain exactly that
site.json (a regular file) with only the hybrid keys (domain, mode, topic, brand, doorway, govAgency); any other file, subdirectory
(even empty or .git), symlink, key or mode is DRIFT. A site.json that is not a JSON object is DRIFT.

Pages are parsed with html.parser (quoted, single-quoted and unquoted attributes; comments ignored), and every
page-like file (*.html, *.htm, *.xhtml, *.xht, *.xml, *.xsl, *.xslt, *.svg, *.shtml, *.php, *.phtml) under the room is
scanned (except .git, node_modules, dot-dirs). This is a static guardrail; the strict CSP below is the enforcement
layer. Besides <script>:
  - on*= event handlers and javascript: URLs are code: declared in overrides.inline like inline scripts
  - iframe/frame srcdoc, object, embed are DRIFT unless declared in overrides.frames; a remote iframe/frame src is
    WARN unless declared; data:/blob:/javascript: frame sources are DRIFT
  - <base href> is DRIFT (it retargets every relative src, including declared modules)
  - N1: every page and room JS file must be UTF-8 (a UTF-8 BOM is fine; a UTF-16/32 BOM, invalid UTF-8 or a NUL
    byte is DRIFT), and a declared charset (meta charset, http-equiv Content-Type, XML encoding) must be utf-8
  - N3: the pin must be a plain <script> start tag that is a direct child of <head> or <body>, with only src,
    integrity, crossorigin="anonymous" and data-site; a page with <frameset> has no live pin. A dead pin is DRIFT
  - N6: <script type=importmap> is DRIFT unless shell.importmap is true; then it must be inline, declared in
    overrides.inline, and map only to local paths
  - CSP rule: every HTML page needs a strict CSP (meta or hosting header; see csp_weak and shell/csp.md). Rooms on
    tools/csp_legacy_rooms.json get WARN until their migration PR; elsewhere it is DRIFT (cspRequired defaults true)
    A meta CSP counts only as the first element in <head> with an exact http-equiv and no comma (D1-D3); subx-factory
    sources must be the page's own pin folder (C1); reCAPTCHA only exact files with shell.recaptcha (C2); Google sign-in's two gapi sources only with
    shell.googleSignIn (C2g); a hosting
    redirect/rewrite to another origin is DRIFT (C3); worker-src/child-src must not be open
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
    listed in shell.redirects (or carrying the nest_stubs.py marker) that fail this test are DRIFT with the reason;
    a shell.redirects entry with .., a backslash, %-encoding, a scheme or a leading // is DRIFT. index.html is never
    a stub
  - C15 noShell inline limits: on a noShell page, declared inline code may not carry "injects" or remote "imports",
    and inline code naming a Firebase SDK URL (gstatic.com/firebasejs, /__/firebase/, an npm CDN firebase package)
    counts as loading the Firebase SDK; so does a keep file loaded on a noShell page whose text names one
  - Comment ends: browsers end a comment at <!-->, <!---> and --!>, which some Python html.parser versions do not.
    Any of the three anywhere in a page is DRIFT (independent of the Python version), so markup hidden behind one
    can never be skipped by the checker while a browser runs it
  - URL normalization: every src, href, import specifier and refresh URL is read the way a browser reads it
    before the local/remote decision (entities decoded once by the parser, leading/trailing C0 controls and spaces
    stripped, tab/CR/LF removed anywhere, \\ read as /, %2e read as . for local paths). Anything that then starts
    with // or a scheme is remote
Runtime injection detection is BEST-EFFORT static analysis: createElement('script') or a non-literal createElement,
import(), importScripts, document.write('<script'), eval, new Function, Worker/SharedWorker, serviceWorker.register.
On a noShell page (N5) its inline code and keep files may also not use Function( (with or without new), eval(,
setTimeout/setInterval with a string, or document.write at all, declared "injects" or not.
Each is DRIFT unless the declaring entry carries "injects": "<reason>"; one that names a factory/shell file is always
DRIFT. Obfuscated code can evade this, so every declared module/keep file still needs human review; its sha256 pins
the reviewed bytes. Any local .js that is a shell copy (release hash or SubX factory header) and is not the declared
fork is DRIFT.

Never writes to the room, Firestore, or the network. Exit 1 with --strict when any room has DRIFT.
"""
import argparse, base64, glob, hashlib, json, os, posixpath, re, subprocess, sys
from collections import Counter
from html import unescape as html_unescape
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
# N2: every served file a browser may render as HTML/XML (case-insensitive extension) is scanned
PAGE_EXTS = ('.html', '.htm', '.xhtml', '.xht', '.xml', '.xsl', '.xslt', '.svg', '.shtml', '.php', '.phtml')
XML_EXTS = ('.xhtml', '.xht', '.xml', '.xsl', '.xslt', '.svg')
# pages that must carry a strict CSP (the CSP rule); .svg/.xml/.xsl(t) take a header CSP only, so they are exempt
CSP_PAGE_EXTS = ('.html', '.htm', '.xhtml', '.xht', '.shtml', '.php', '.phtml')
# B12: JS lets a comment stand wherever whitespace may, so every gap between tokens below also skips comments.
# N4: U+FEFF is JS whitespace (Python's \s misses it); a line comment also ends at CR, U+2028 and U+2029
JS_GAP = r"""(?:[\s\ufeff]|/\*[\s\S]*?\*/|//[^\n\r\u2028\u2029]*)*"""
INJECT_RE = re.compile((r"""createElement(?:NS)?G\([^)]*?['"`]script['"`]G\)|createElementG\(G[^'"`\s\ufeff)/]|\bimportG\("""
                        r"""|\bimportScriptsG\(|document\s*\.\s*write(?:ln)?\s*\([^)]*<\s*script|\bevalG\(|[(,=:]G\s*evalG[),;]"""
                        r"""|\bnew(?:[\s\ufeff]|/\*[\s\S]*?\*/)+FunctionG\(|(?-i:(?<![\w$.])Function)G\("""
                        r"""|\bnew(?:[\s\ufeff]|/\*[\s\S]*?\*/)+(?:Shared)?WorkerG\("""
                        r"""|serviceWorkerG\.G\s*register""").replace('G', JS_GAP), re.I)
# N5: string-to-code sinks a keep file on a noShell page may never use (with or without a declared "injects")
NS_EVAL_RE = re.compile((r"""(?<![\w$.])FunctionG\(|\bevalG\(|\bset(?:Timeout|Interval)G\(G['"`]"""
                         r"""|\bdocumentG(?:\.G|\[G['"`])write""").replace('G', JS_GAP))
# static ES module imports / re-exports: import x from 'spec', import 'spec', export {a} from 'spec'. Comments may
# sit anywhere between the tokens (/**/import, import/**/'x', from/**/'x'); they are skipped, not trusted (B12)
IMPORT_RE = re.compile((r"""(?:^|(?<=[\s\ufeff;{}/)]))(?:import|export)G(?:(?:[\w*{}\s\ufeff,$]|/\*[\s\S]*?\*/|//[^\n\r\u2028\u2029]*[\n\r\u2028\u2029])*?(?<![\w$])fromG)?"""
                        r"""(['"])([^'"\n]*)\1""").replace('G', JS_GAP), re.M)
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
        self.forms, self.comments, self.comment_traps, self.tags = [], [], [], []
        self._ctx = {t: 0 for t in INERT_CTX}

    def feed(self, data):
        self.raw = getattr(self, 'raw', '') + data
        super().feed(data)

    @property
    def toks(self):
        """The page as a browser's tokenizer reads it (browser_tokens), for the B8-B10 checks and C14/C15 grammar."""
        if getattr(self, '_toks_for', None) != len(self.raw):
            self._toks, self._toks_for = browser_tokens(self.raw), len(self.raw)
        return self._toks

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
        self.tags.append((tag, tuple((k.lower(), v) for k, v in attrs)))
        a, dup = self._attrs(tag, attrs, line)
        if tag == 'script':
            # SVG <script> loads its source from href / xlink:href, not src (C7)
            if 'src' not in a and (self._ctx['svg'] or self._ctx['math']):
                for k in ('href', 'xlink:href'):
                    if a.get(k) is not None:
                        a['src'] = a[k]
                        break
            rec = {'attrs': a, 'dup': dup, 'inert': [t for t in INERT_CTX if self._ctx[t]], 'line': line,
                   'key': self.tags[-1]}
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


def decode_utf8(data):
    """N1: (text, issues). Pages and room JS must be UTF-8: a UTF-16/UTF-32 byte-order mark, a NUL byte or bytes that
    are not valid UTF-8 make a browser (or the checker) read different characters, so each is an issue (DRIFT).
    A UTF-8 BOM is fine and is stripped, as browsers do."""
    issues = []
    if data.startswith((b'\x00\x00\xfe\xff', b'\xff\xfe\x00\x00')):
        issues.append('a UTF-32 byte-order mark')
    elif data.startswith((b'\xfe\xff', b'\xff\xfe')):
        issues.append('a UTF-16 byte-order mark')
    if b'\x00' in data:
        issues.append('NUL bytes')
    if data.startswith(b'\xef\xbb\xbf'):
        data = data[3:]
    try:
        text = data.decode('utf-8')
    except UnicodeDecodeError as e:
        issues.append('bytes that are not valid UTF-8 (first at offset %d)' % e.start)
        text = data.decode('utf-8', 'replace')
    # newline normalization, as a browser's input stream (and the old text-mode read) does; CR ends a JS line too
    return text.replace('\r\n', '\n').replace('\r', '\n'), issues


UTF8_LABELS = ('utf-8', 'utf8', 'unicode-1-1-utf-8')


def charset_findings(raw, toks):
    """N1: a declared charset other than UTF-8 (<meta charset>, http-equiv Content-Type, <?xml encoding?>,
    <script charset>) makes a browser decode the bytes differently from the checker."""
    f = []
    for t in toks:
        if t['kind'] != 'start' or t['name'] not in ('meta', 'script'):
            continue
        a = {}
        for k, v in t['attrs']:
            a.setdefault(k, html_unescape(v or ''))
        cs = []
        if 'charset' in a:
            cs.append(('charset', a['charset']))
        if t['name'] == 'meta' and a.get('http-equiv', '').strip().lower() == 'content-type':
            m = re.search(r'charset\s*=\s*["\']?([^"\';\s]*)', a.get('content', ''), re.I)
            if m:
                cs.append(('http-equiv Content-Type charset', m.group(1)))
        for what, v in cs:
            if v.strip().lower() not in UTF8_LABELS:
                f.append('%d <%s %s=%r>: a declared charset other than utf-8 (the page must be UTF-8)'
                         % (_ln(raw, t['pos']), t['name'], what, v[:30]))
    m = re.match(r'\s*<\?xml[^>]*?\bencoding\s*=\s*["\']([^"\']*)', raw)
    if m and m.group(1).strip().lower() not in UTF8_LABELS:
        f.append('1 <?xml encoding=%r?>: a declared charset other than utf-8 (the page must be UTF-8)' % m.group(1)[:30])
    return f


def pages(room):
    """(relpath, parsed _Page) for every page-like file. Comments are not markup."""
    for page in walk(room, PAGE_EXTS):
        p = _Page()
        raw, p.enc = decode_utf8(open(page, 'rb').read())
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
    """An HTML attribute URL as the browser's URL parser sees it (attribute entities are already decoded once by the
    parser): strip leading/trailing C0 controls and spaces, drop tab/CR/LF anywhere, read \\ as / (http(s) pages).
    HTML attributes only: JS specifiers go through norm_js (B11)."""
    u = re.sub(r'^[\x00-\x20]+|[\x00-\x20]+$', '', u or '')
    return re.sub(r'[\t\n\r]', '', u).replace('\\', '/')


def norm_js(u):
    """A JS module specifier as the URL parser sees it. Unlike an HTML attribute, \\ is a JS string escape, so
    callers reject specifiers that contain one (B11) rather than read it as /."""
    u = re.sub(r'^[\x00-\x20]+|[\x00-\x20]+$', '', u or '')
    return re.sub(r'[\t\n\r]', '', u)


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


def csp_policies(text, single=False):
    """A Content-Security-Policy value -> list of policies, each {directive: [sources]}. In a header value a comma
    separates several policies; a <meta> delivers ONE policy (single=True), where a comma is just part of a value."""
    out = []
    for pol in ([text or ''] if single else (text or '').split(',')):
        d = {}
        for part in pol.split(';'):
            toks = [x for x in CSP_WS_RE.split(part) if x]  # ASCII whitespace only, as browsers split (B1)
            if toks and _ascii_lower(toks[0]) not in d:  # first occurrence of a directive wins
                d[_ascii_lower(toks[0])] = toks[1:]
        if d:
            out.append(d)
    return out


CSP_WS_RE = re.compile(r'[\t\n\f\r ]+')
CSP_BAD_CHAR_RE = re.compile(r'[^\t\n\f\r\x21-\x7e ]')


def _ascii_lower(x):
    return x.translate({c: c + 32 for c in range(65, 91)})


def csp_syntax_bad(text):
    """B1: why a CSP value is not plain CSP syntax (None = fine). Browsers split only on TAB, LF, FF, CR and SPACE, so
    NBSP, U+2028, \\v or \\x1f glue a directive name to its sources and the browser drops it (a later weak duplicate
    then wins). Any character outside printable ASCII plus those five, or a directive name outside [a-z0-9-], is
    DRIFT."""
    m = CSP_BAD_CHAR_RE.search(text or '')
    if m:
        return ('the CSP value has character U+%04X: only printable ASCII and tab/LF/FF/CR/space are allowed (browsers '
                'do not split on other whitespace, so the directive is dropped)' % ord(m.group(0)))
    for pol in (text or '').split(','):
        for part in pol.split(';'):
            toks = [x for x in CSP_WS_RE.split(part) if x]
            if toks and not re.fullmatch(r'^[a-z0-9-]+$', _ascii_lower(toks[0])):
                return 'the CSP has an invalid directive name %r (browsers drop it)' % toks[0][:40]
    return None


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
        m = HOST_SRC_RE.fullmatch(x)
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


# ---- CSP rule: every HTML page carries a strict CSP (meta tag, or a header rule from the hosting config) ----
CSP_LEGACY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'csp_legacy_rooms.json')
# host sources a strict script-src may list: the pin path with its full 40-char commit SHA, and exact-version paths
PIN_SRC_RE = re.compile(r'^https://cdn\.jsdelivr\.net/gh/jebbdykstra99/subx-factory@[0-9a-f]{40}/\S*$')
FIREBASE_SRC_RE = re.compile(r'^https://www\.gstatic\.com/firebasejs/\d+\.\d+\.\d+/\S*$')
EMOJI_SRC_RE = re.compile(r'^https://cdn\.jsdelivr\.net/npm/emoji-picker-element@(\d+\.\d+\.\d+)/\S*$')
# reCAPTCHA (Firebase App Check), only with shell.recaptcha: true. Exact files on www.google.com and the releases/
# folder on gstatic: the rest of /recaptcha/ on both hosts serves a public AngularJS gadget (a CSP bypass)
RECAPTCHA_SRCS = ('https://www.google.com/recaptcha/api.js', 'https://www.google.com/recaptcha/enterprise.js',
                  'https://www.gstatic.com/recaptcha/releases/')
# Google sign-in helper (Firebase Auth signInWithPopup / signInWithRedirect load gapi), only with shell.googleSignIn:
# true. The exact loader file and the abc-static module folder it loads gapi_iframes from; nothing else on the host
GOOGLE_SIGNIN_SRCS = ('https://apis.google.com/js/api.js', 'https://apis.google.com/_/scs/abc-static/')
SUBX_SRC_RE = re.compile(r'^(?:https?://)?cdn\.jsdelivr\.net/gh/jebbdykstra99/subx-factory', re.I)
CSP_WEAK_KEYWORDS = ("'unsafe-inline'", "'unsafe-eval'", "'unsafe-hashes'", "'wasm-unsafe-eval'", "'strict-dynamic'",
                     "'unsafe-allow-redirects'", "'inline-speculation-rules'")


def load_csp_legacy(path=None):
    """Site ids of the rooms that predate the CSP rule (tools/csp_legacy_rooms.json): a missing or weak CSP is WARN
    for them, DRIFT for every other room."""
    try:
        d = json.load(open(path or CSP_LEGACY_FILE))
        return {x for x in (d.get('rooms') if isinstance(d, dict) else d) or [] if isinstance(x, str)}
    except Exception:
        return set()


def script_hash_sources(text):
    """The CSP hash sources for an inline script's text (browsers hash the text after newline normalization)."""
    b = text.replace('\r\n', '\n').replace('\r', '\n').encode('utf-8')
    return {"'%s-%s'" % (alg, base64.b64encode(getattr(hashlib, alg)(b).digest()).decode()) for alg in ('sha256', 'sha384', 'sha512')}


def pin_dirs_of(pg):
    """C1: the script-src folders a page's own pin allows: .../subx-factory@<pin sha>/shell/<version>/ (or the
    pre-merge .../@<sourceCommit>/factory/)."""
    out = set()
    for s_ in pg.out:
        if s_.get('inert'):
            continue
        u = norm_url(s_['attrs'].get('src'))
        m, pre = PIN_RE.fullmatch(u), PRE_RE.fullmatch(u)
        if m:
            out.add('https://%s%s%s/shell/%s/' % (PIN_HOST, PIN_PATH, m.group(1), m.group(2)))
        elif pre:
            out.add('https://%s%s%s/factory/' % (PIN_HOST, PIN_PATH, pre.group(1)))
    return out


def csp_weak(policy, room_hashes, has_pin, pin_dirs=(), recaptcha=False, google_signin=False):
    """Why one CSP policy is not strict ([] = strict). Strict: script-src (or default-src) lists only 'self', 'none',
    hashes of the room's redirect-stub / 404.html inline scripts, the page's own pin folder (pin_dirs: its 40-char
    commit SHA and exact /shell/v<base>/ path, C1; no other subx-factory source), and exact-version Firebase /
    emoji-picker-element paths (reCAPTCHA's exact files only with shell.recaptcha, C2; Google sign-in's exact gapi
    sources only with shell.googleSignIn, C2g); no unsafe-*, nonce,
    strict-dynamic, wildcard or scheme source; worker-src / child-src not open; object-src 'none'; base-uri 'none'."""
    why = []
    srcs = policy.get('script-src', policy.get('default-src'))
    if srcs is None:
        return ['no script-src or default-src']
    lists = [('script-src' if 'script-src' in policy else 'default-src', srcs)] + \
        [(k, policy[k]) for k in ('script-src-elem', 'script-src-attr') if k in policy]
    pin_listed = False
    for dname, lst in lists:
        for x in lst:
            lx = x.lower()
            if lx in ("'self'", "'none'", "'report-sample'"):
                continue
            if lx in CSP_WEAK_KEYWORDS:
                why.append('%s has %s' % (dname, x))
            elif lx.startswith("'nonce-"):
                why.append('%s has a nonce (a static page cannot rotate it)' % dname)
            elif re.match(r"^'sha(?:256|384|512)-", lx):
                if x not in room_hashes:
                    why.append('%s lists hash %s that matches no redirect-stub or 404.html inline script (the only '
                               'inline scripts a strict CSP may allow)' % (dname, x[:20]))
            elif x.startswith("'"):
                why.append('%s has unknown keyword %s' % (dname, x))
            elif SUBX_SRC_RE.match(x) and (x in pin_dirs or any(x == d_ + f_ for d_ in pin_dirs for f_ in SHELL_FILES)):
                pin_listed = True
            elif PIN_SRC_RE.fullmatch(x):
                why.append("%s source %s is not this page's pin folder (%s): every subx-factory source must use the "
                           "pin's commit SHA and its exact /shell/v<base>/ folder" % (dname, x[:110], ', '.join(sorted(pin_dirs)) or 'no pin'))
            elif EMOJI_SRC_RE.fullmatch(x) or FIREBASE_SRC_RE.fullmatch(x):
                continue
            elif lx in RECAPTCHA_SRCS:
                if not recaptcha:
                    why.append('%s source %s is a reCAPTCHA source: allowed only when the room sets shell.recaptcha: '
                               'true' % (dname, x))
            elif lx in GOOGLE_SIGNIN_SRCS:
                if not google_signin:
                    why.append('%s source %s is a Google sign-in source: allowed only when the site sets '
                               'shell.googleSignIn: true' % (dname, x))
            elif 'jsdelivr' in lx and 'subx-factory' in lx or lx.rstrip('/') in ('https://cdn.jsdelivr.net', 'cdn.jsdelivr.net'):
                why.append('%s source %s is not the full pinned path with the 40-char commit SHA (bare host, repo path, '
                           'tag or branch)' % (dname, x[:80]))
            else:
                why.append('%s source %s is not allowed in a strict CSP (wildcard, scheme, or a host path that is not '
                           'pinned to an exact version)' % (dname, x[:80]))
    if has_pin and not pin_listed:
        why.append("script-src does not list this page's pin folder (https://cdn.jsdelivr.net/gh/jebbdykstra99/"
                   'subx-factory@<pin sha>/shell/v<base>/)')
    for dname in ('worker-src', 'child-src'):
        for x in policy.get(dname) or []:
            lx = x.lower()
            if lx in ('*', 'https:', 'http:', 'data:') or lx.startswith('*') or re.match(r'^(?:https?://)?\*', lx):
                why.append('%s has %s (a worker may load from anywhere)' % (dname, x))
    obj = policy.get('object-src', policy.get('default-src'))
    if obj is None or [x.lower() for x in obj] != ["'none'"]:
        why.append("object-src is not 'none'")
    if [x.lower() for x in policy.get('base-uri') or []] != ["'none'"]:
        why.append("base-uri is not 'none'")
    return why


def meta_csps(pg):
    """[(line, [policy], placement problem or None)] for every <meta http-equiv=Content-Security-Policy>, as a browser
    tokenizes the page. A meta CSP counts only as the first element in <head> (D1): before it only <!DOCTYPE>,
    <html>, <head>, </head>, <meta charset>, other CSP metas, comments and whitespace. Anything else can make the
    tree builder close <head> (a <div>, text, an <img>), so the meta lands in <body> where browsers ignore it, or
    leaves earlier content uncovered. http-equiv is matched exactly, case-insensitively, with no trimming (D3), and
    a meta delivers one policy, so a comma in it is DRIFT (D2)."""
    toks, raw = pg.toks, pg.raw
    ctx, _ = tree_ctx(toks)
    first_script = next((i for i, t in enumerate(toks) if t['kind'] == 'start' and t['name'] == 'script'), None)
    out, prefix_ok, prev = [], True, 0
    for i, t in enumerate(toks):
        if raw[prev:t['pos']].strip('\t\n\f\r '):
            prefix_ok = False  # non-whitespace text
        prev = t.get('stop', t['pos'])
        a = {}
        for k, v in t.get('attrs') or []:
            a.setdefault(k, html_unescape(v or ''))
        equiv = a.get('http-equiv', '') if t['kind'] == 'start' and t['name'] == 'meta' else ''
        if equiv.strip('\t\n\f\r ').lower() == 'content-security-policy':
            content = a.get('content', '')
            bad = None
            if equiv.lower() != 'content-security-policy':
                bad = ('http-equiv=%r has surrounding whitespace: browsers match it exactly and ignore this policy'
                       % equiv)
            elif not prefix_ok:
                bad = ('the meta CSP is not the first element in <head> (only <meta charset>, comments and whitespace '
                       'may come before it; other content can move it into <body>, where browsers ignore it)')
            elif not set(ctx.get(i, ())) <= {'html', 'head'}:
                bad = 'the meta CSP is not inside <head> (browsers ignore it there)'
            elif first_script is not None and first_script < i:
                bad = 'the meta CSP comes after a <script> (it does not cover scripts before it)'
            elif ',' in content:
                bad = ('the meta CSP contains a comma: a <meta> delivers one policy, so a browser reads the comma and '
                       'what follows as more sources of the same directive')
            elif csp_syntax_bad(content):
                bad = csp_syntax_bad(content)
            out.append((_ln(raw, t['pos']), csp_policies(content, single=True), bad))
            continue
        if not prefix_ok:
            continue
        if t['kind'] == 'comment' or (t['kind'] == 'decl' and t['text'].strip().lower().startswith('doctype')):
            continue
        if t['kind'] == 'start' and t['name'] in ('html', 'head') or t['kind'] == 'end' and t['name'] == 'head':
            continue
        if t['kind'] == 'start' and t['name'] == 'meta' and 'charset' in a and not equiv:
            continue
        prefix_ok = False
    return out


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


def hosting_redirects(room):
    """C3: hosting redirects or rewrites to another origin are DRIFT. After a redirect CSP no longer checks the path,
    so a 'self' URL redirected to an allowed host (cdn.jsdelivr.net) could load any file on it."""
    out = []

    def ext(fn_, src, dest):
        d = norm_url(str(dest or ''))
        if REMOTE_RE.match(d):
            out.append('%s sends %s to an outside origin (%s): hosting redirects and rewrites must stay on the room '
                       "origin (after a redirect CSP ignores the path)" % (fn_, src or '?', d[:100]))
    p = os.path.join(room, '_redirects')
    if os.path.isfile(p):
        for line in open(p, encoding='utf-8', errors='replace').read().splitlines():
            parts = line.split('#', 1)[0].split()
            if len(parts) >= 2:
                ext('_redirects', parts[0], parts[1])
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
            k = k.strip().lower()
            if k == 'location':
                ext('_headers Location', pat, v.strip())
            elif k == 'refresh':
                m = re.search(r'url\s*=\s*(\S+)', v, re.I)
                if m:
                    ext('_headers Refresh', pat, m.group(1).strip('\'"'))
    for fn_ in ('firebase.json', 'vercel.json'):
        p = os.path.join(room, fn_)
        if not os.path.isfile(p):
            continue
        try:
            j = json.load(open(p))
        except Exception:
            continue  # header_csps already warns
        sites = j.get('hosting') or [] if fn_ == 'firebase.json' else j
        for site in (sites if isinstance(sites, list) else [sites]):
            if not isinstance(site, dict):
                continue
            for key in ('redirects', 'rewrites'):
                for e in site.get(key) or []:
                    if isinstance(e, dict):
                        ext('%s %s' % (fn_, key), e.get('source') or e.get('regex'), e.get('destination'))
    if os.path.isfile(os.path.join(room, 'vercel.json')):
        try:
            j = json.load(open(os.path.join(room, 'vercel.json')))
        except Exception:
            j = {}
        # vercel legacy routes[]: dest (proxy or redirect) and a Location header; a Location in headers[] too
        for e in (j.get('routes') or []) if isinstance(j, dict) else []:
            if isinstance(e, dict):
                ext('vercel.json routes', e.get('src'), e.get('dest'))
                h = e.get('headers')
                for k, v in (h.items() if isinstance(h, dict) else []):
                    if str(k).strip().lower() == 'location':
                        ext('vercel.json routes Location', e.get('src'), v)
        for e in (j.get('headers') or []) if isinstance(j, dict) else []:
            for h in (e.get('headers') or []) if isinstance(e, dict) else []:
                if isinstance(h, dict) and str(h.get('key') or '').strip().lower() == 'location':
                    ext('vercel.json headers Location', e.get('source'), h.get('value'))
    p = os.path.join(room, 'netlify.toml')
    if os.path.isfile(p):
        try:
            import tomllib
            for e in tomllib.load(open(p, 'rb')).get('redirects') or []:
                ext('netlify.toml redirects', e.get('from'), e.get('to'))
        except Exception:
            pass
    return out


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
    m = re.fullmatch(r'^\s*[\d.]*\s*[;,]?\s*(?:url\s*=\s*)?(.*)$', content or '', re.I | re.S)
    u = (m.group(1) if m else '').strip()
    if u[:1] in '\'"' and u:
        u = u[1:].split(u[0], 1)[0]
    return u.strip()


CSS_IMPORT_RE = re.compile(r"""@import\s+(?:url\(\s*)?['"]?([^'")\s;]+)""", re.I)
CSS_JSURL_RE = re.compile(r"""url\(\s*['"]?\s*javascript:""", re.I)


def css_notes(text):
    out = []
    for m in CSS_IMPORT_RE.finditer(text):
        if '\\' in m.group(1):  # CSS escapes (\2f, \/) are decoded before the URL is parsed
            out.append('CSS @import with a backslash escape %s' % m.group(1))
        elif REMOTE_RE.match(norm_js(m.group(1))) and not m.group(1).lower().startswith('data:'):
            out.append('CSS @import of remote %s' % m.group(1))
    if CSS_JSURL_RE.search(text):
        out.append('CSS url(javascript:...) (inert in current browsers)')
    return out


# ---- B8-B10 and C14/C15 allowlist: a small tokenizer that follows the HTML spec's tokenizer states (data, tag,
# comment, bogus comment, doctype, RCDATA/RAWTEXT/script data, plaintext). It does not build a tree. It is used
# to compare against html.parser, and to hold redirect stubs and noShell pages to a small accepted grammar.
RAW_TEXT = ('textarea', 'title', 'noscript', 'iframe', 'xmp', 'noembed', 'noframes')  # RCDATA/RAWTEXT (noscript: scripting on)
RAW_ALL = RAW_TEXT + ('script', 'style')
_WS = '\t\n\f\r '
_TAGNAME_RE = re.compile(r'[^\t\n\f\r />]*')
_ATTRNAME_RE = re.compile(r'[^\t\n\f\r />][^\t\n\f\r /=>]*')
_EQ_RE = re.compile(r'[\t\n\f\r ]*=[\t\n\f\r ]*')
_UNQ_RE = re.compile(r'[^\t\n\f\r >]*')
_CEND_RE = re.compile(r'--!?>')


def browser_tokens(raw):
    """Tokens as a browser's tokenizer reads the page (HTML namespace only; foreign content is handled by the callers
    conservatively). Each token is a dict with kind start|end|comment|decl|bogus|raw and pos (offset)."""
    out, i, n = [], 0, len(raw)
    while i < n:
        j = raw.find('<', i)
        if j < 0:
            break
        i, nx = j, raw[j + 1:j + 2]
        if raw.startswith('<!--', i):
            if raw.startswith('<!-->', i) or raw.startswith('<!--->', i):
                k = raw.find('>', i + 4)
                out.append({'kind': 'comment', 'text': raw[i + 4:k], 'pos': i, 'stop': k + 1})
                i = k + 1
                continue
            m = _CEND_RE.search(raw, i + 4)
            out.append({'kind': 'comment', 'text': raw[i + 4:m.start() if m else n], 'pos': i, 'stop': m.end() if m else n})
            i = m.end() if m else n
            continue
        if nx in ('!', '?') or (nx == '/' and raw[i + 2:i + 3] and raw[i + 2] != '>'
                                and not (raw[i + 2].isascii() and raw[i + 2].isalpha())):
            k = raw.find('>', i + 2)  # doctype, bogus comment (<!x, <?x, </1): all end at the first >
            out.append({'kind': 'decl' if nx == '!' else 'bogus', 'text': raw[i + 2:k if k >= 0 else n], 'pos': i,
                        'stop': k + 1 if k >= 0 else n})
            i = k + 1 if k >= 0 else n
            continue
        if nx == '/' and raw[i + 2:i + 3] in ('>', ''):
            i += 3
            continue
        end = nx == '/'
        k = i + 2 if end else i + 1
        if not (raw[k:k + 1].isascii() and raw[k:k + 1].isalpha()):
            i += 1  # a literal '<'
            continue
        name = _TAGNAME_RE.match(raw, k).group(0).lower()
        k += len(name)
        attrs, closed, done = [], False, False
        while k < n:
            c = raw[k]
            if c in _WS:
                k += 1
            elif c == '>':
                k += 1
                done = True
                break
            elif c == '/':
                if raw[k + 1:k + 2] == '>':
                    closed, done, k = True, True, k + 2
                    break
                k += 1
            else:
                an = _ATTRNAME_RE.match(raw, k).group(0)
                k += len(an)
                val, m = None, _EQ_RE.match(raw, k)
                if m:
                    k = m.end()
                    if raw[k:k + 1] in ('"', "'"):
                        e = raw.find(raw[k], k + 1)
                        e = n if e < 0 else e
                        val, k = raw[k + 1:e], e + 1
                    else:
                        val = _UNQ_RE.match(raw, k).group(0)
                        k += len(val)
                attrs.append((an.lower(), val))
        if not done:
            break  # EOF in a tag: the browser drops the tag
        out.append({'kind': 'end' if end else 'start', 'name': name, 'attrs': attrs, 'closed': closed, 'pos': i, 'stop': k})
        i = k
        if end:
            continue
        if name == 'plaintext':
            out.append({'kind': 'raw', 'name': name, 'text': raw[k:], 'pos': k, 'stop': n})
            break
        if name in RAW_ALL:  # a self-closing flag is ignored on these: the content still runs to </name
            m = re.compile(r'</%s[\t\n\f\r />]' % re.escape(name), re.I).search(raw, k)
            e = m.start() if m else n
            out.append({'kind': 'raw', 'name': name, 'text': raw[k:e], 'pos': k, 'attrs': attrs, 'stop': e})
            i = e
    return out


def _ln(raw, pos):
    return raw.count('\n', 0, pos) + 1


def _attr_key(name, attrs):
    return (name, tuple((k, html_unescape(v) if v is not None else None) for k, v in attrs))


VOID_EL = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr',
           'basefont', 'bgsound', 'frame', 'keygen'}
_P_CLOSERS = {'address', 'article', 'aside', 'blockquote', 'details', 'div', 'dl', 'fieldset', 'figcaption', 'figure',
              'footer', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'header', 'hgroup', 'hr', 'main', 'menu', 'nav', 'ol',
              'p', 'pre', 'section', 'table', 'ul'}
_IMPLIED = {'li': ('li',), 'option': ('option',), 'dt': ('dt', 'dd'), 'dd': ('dt', 'dd'), 'tr': ('tr', 'td', 'th'),
            'td': ('td', 'th'), 'th': ('td', 'th')}


def tree_ctx(toks):
    """N3: a small, conservative open-element stack over browser_tokens. Returns ({token index: tuple of open
    ancestors} for every <script> and <meta> start tag, whether any <frameset> start tag appears). A self-closing
    flag is honoured only on void elements and inside svg/math (as browsers do); a few implied end tags (p, li,
    option, dt/dd, table cells and rows) are applied. Anything it cannot model leaves an extra ancestor, which reads
    as "not a direct child of <head>/<body>" (DRIFT), never the other way round."""
    stack, ctx, frameset = [], {}, False
    for i, t in enumerate(toks):
        if t['kind'] == 'start':
            n = t['name']
            if n == 'frameset':
                frameset = True
            if n in ('script', 'meta'):
                ctx[i] = tuple(stack)
            if n == 'body' and 'head' in stack:  # <body> implicitly closes <head>
                del stack[stack.index('head'):]
            if stack and (stack[-1] == 'p' and n in _P_CLOSERS or stack[-1] in _IMPLIED.get(n, ())):
                stack.pop()
            if n in VOID_EL or (t['closed'] and ('svg' in stack or 'math' in stack or n in ('svg', 'math'))):
                continue
            stack.append(n)
        elif t['kind'] == 'end' and t['name'] in stack:
            del stack[len(stack) - 1 - stack[::-1].index(t['name']):]
    return ctx, frameset


PIN_ATTRS = ('src', 'integrity', 'crossorigin', 'data-site')  # the real template; factory-rail.js omits data-site


def pin_form(pg, rec):
    """N3: problems with a pin <script> (a py _Page record) as a browser reads it: it must be a plain classic
    <script> start tag the browser also sees, a direct child of <head> or <body> (no other ancestor than <html>),
    with only the template attributes, and no <frameset> anywhere on the page. [] = the pin is live."""
    toks = pg.toks
    ctx, frameset = tree_ctx(toks)
    hits = [i for i, t in enumerate(toks) if t['kind'] == 'start' and t['name'] == 'script'
            and _attr_key('script', t['attrs']) == rec['key']]
    out = []
    if frameset:
        out.append('the page has a <frameset> (a browser then never runs the body)')
    if not hits:
        out.append('a browser does not see this <script> start tag (it sits inside raw text such as <noscript>, '
                   '<textarea>, <title>, <iframe> or an earlier unclosed tag)')
        return out
    for i in hits:
        anc = [x for x in ctx.get(i, ()) if x != 'html']
        if not (anc in (['head'], ['body'], []) or anc == ['head', 'body']):
            out.append('it is not a direct child of <head> or <body> (open ancestors: %s)' % ' > '.join(ctx.get(i, ())))
        extra = sorted({k for k, _ in toks[i]['attrs']} - set(PIN_ATTRS))
        if extra:
            out.append('it carries attributes outside the pin template (%s): only %s are allowed'
                       % (', '.join(extra), ', '.join(PIN_ATTRS)))
    return list(dict.fromkeys(out))


def xml_findings(raw, toks):
    """N2: XML-family pages (.xhtml .xht .xml .xsl .xslt .svg): a prefixed <x:script> runs in the XHTML namespace and
    an <?xml-stylesheet?> can run an XSLT that writes script; neither is visible to the HTML checks."""
    f = []
    for t in toks:
        if t['kind'] in ('start', 'end') and ':' in t['name'] and t['name'].rsplit(':', 1)[1] in ('script', 'iframe', 'object', 'embed', 'foreignobject'):
            f.append('%d <%s>: a namespace-prefixed element the checker does not read as HTML' % (_ln(raw, t['pos']), t['name']))
        if t['kind'] == 'bogus' and re.match(r'(?i)xml-stylesheet\b', t['text']) and not re.search(r'(?i)type\s*=\s*["\']text/css', t['text']):
            f.append('%d <?%s>: an XSLT stylesheet can generate script' % (_ln(raw, t['pos']), t['text'][:40]))
    return list(dict.fromkeys(f))


def prescan(raw, toks, pg):
    """B8-B10 (all pages): markup that html.parser and a browser read differently. Returns findings (str)."""
    f = []
    foreign = None  # offset of the first <svg>/<math>: after it the browser may be in foreign content
    for t in toks:
        if t['kind'] == 'start' and t['name'] in ('svg', 'math') and foreign is None:
            foreign = t['pos']
        if t['kind'] != 'raw':
            continue
        where = '%d <%s>' % (_ln(raw, t['pos']), t['name'])
        if t['name'] == 'plaintext':
            f.append('%s: everything after <plaintext> is text to a browser but markup to the checker' % where)
        elif '<!--' in t['text'] and t['name'] in RAW_TEXT:
            f.append('%s contains <!--: browsers read it as text, the checker as a comment that can hide markup' % where)
        elif '<!--' in t['text'] and t['name'] == 'script':
            f.append('%s script text contains <!--: browsers can then run past the first </script> '
                     '(script double-escape)' % where)
        elif foreign is not None and t['pos'] > foreign and re.search(r'<[A-Za-z!/?]', t['text']):
            f.append('%s contains markup after an <svg>/<math>: in foreign content a browser parses it as tags' % where)
    for m in re.finditer(r'<!\[', raw):
        f.append('%d has <![ (CDATA or marked section): browsers end it at the first > outside svg/math, the checker '
                 'at ]]>' % _ln(raw, m.start()))
    for t in toks:
        if t['kind'] == 'decl' and not re.fullmatch(r'(?i)^doctype[\t\n\f\r ]+html[\t\n\f\r ]*$', t['text']):
            f.append('%d has <!%s>: only <!DOCTYPE html> is allowed (browsers end a declaration at the first >)'
                     % (_ln(raw, t['pos']), t['text'][:30]))
    # differential: every start tag the browser sees must be one the checker saw, with the same attributes, and
    # every inline script text must be the text the checker hashed
    mine = Counter(_attr_key(t['name'], t['attrs']) for t in toks if t['kind'] == 'start')
    py = Counter((n_, tuple(a_)) for n_, a_ in pg.tags)
    for (name, attrs), c in sorted((mine - py).items(), key=str):
        pos = next(t['pos'] for t in toks if t['kind'] == 'start' and _attr_key(t['name'], t['attrs']) == (name, attrs))
        f.append('%d a browser sees <%s%s> that the checker does not (parsers disagree)'
                 % (_ln(raw, pos), name, ''.join(' %s=%r' % kv for kv in attrs)[:80]))
    # N3/C18: and the other way round: a start tag the checker sees that a browser does not (it sits in raw text)
    for (name, attrs), c in sorted((py - mine).items(), key=str):
        f.append('a <%s%s> the checker sees is raw text to a browser (parsers disagree)'
                 % (name, ''.join(' %s=%r' % kv for kv in attrs)[:80]))
    my_txt = Counter(t['text'] for t in toks if t['kind'] == 'raw' and t['name'] == 'script'
                     and not any(k in ('src', 'href', 'xlink:href') for k, _ in t['attrs']))
    py_txt = Counter(s['text'] for s in pg.out if s['attrs'].get('src') is None)
    for txt in sorted(my_txt - py_txt):
        pos = next(t['pos'] for t in toks if t['kind'] == 'raw' and t['name'] == 'script' and t['text'] == txt)
        f.append('%d a browser runs inline script text %r that the checker does not see as one script (parsers disagree)'
                 % (_ln(raw, pos), txt[:60]))
    return f


NEST_COMMENT = ' %s; edit site.json, not this file ' % NEST_MARK
# the factory/404.html restore-path bounce, byte for byte (C15: the one inline script a noShell page may carry)
NOTFOUND_TEMPLATE = (
    "\n    (function () {\n"
    "      var path = location.pathname || '/';\n"
    "      if (path.charAt(0) !== '/') path = '/' + path;\n"
    "      try { sessionStorage.setItem('subx.restorePath', path + (location.search || '') + (location.hash || '')); } catch (e) {}\n"
    "      location.replace('/' + (location.search || '') + (location.hash || ''));\n"
    "    })();\n  ")
CLASSIC_TYPES = ('', 'text/javascript', 'application/javascript', 'text/ecmascript', 'application/ecmascript')


def strict_grammar(pg, kind):
    """C14/C15 allowlist: redirect stubs (kind 'stub') and noShell pages (kind 'noShell') must stay inside a small
    grammar, so no parser difference can hide code on them. Returns the violations as 'line: what' strings."""
    raw, v = pg.raw, []
    for t in pg.toks:
        ln, k = _ln(raw, t['pos']), t['kind']
        if k == 'comment':
            if t['text'] != NEST_COMMENT:
                v.append('%d: a comment <!--%s-->' % (ln, t['text'][:40]))
        elif k == 'decl':
            if not re.fullmatch(r'(?i)^doctype[\t\n\f\r ]+html[\t\n\f\r ]*$', t['text']):
                v.append('%d: <!%s>' % (ln, t['text'][:40]))
        elif k == 'bogus':
            v.append('%d: a bogus comment <%s%s>' % (ln, raw[t['pos'] + 1], t['text'][:40]))
        elif k == 'start':
            for an, av in t['attrs']:
                av = html_unescape(av or '')
                if an.startswith('on') or _jsurl(av):
                    v.append('%d: inline code in <%s %s=>' % (ln, t['name'], an))
            if t['name'] == 'script' and kind == 'stub' and any(an in ('src', 'href', 'xlink:href') for an, _ in t['attrs']):
                v.append('%d: an external <script>' % ln)
        elif k == 'raw':
            if t['name'] == 'plaintext' or '<' in t['text']:
                v.append('%d: <%s> whose content contains <' % (ln, t['name']))
            if t['name'] != 'script' or any(an in ('src', 'href', 'xlink:href') for an, _ in t['attrs']):
                continue
            typ = html_unescape(dict(reversed(t['attrs'])).get('type') or '').strip().lower()
            text = t['text'].replace('\r\n', '\n')
            if typ in CLASSIC_TYPES:
                if not (NEST_RE.fullmatch(text) or BARE_RE.fullmatch(text) or (kind == 'noShell' and text == NOTFOUND_TEMPLATE)):
                    v.append('%d: an inline <script> that is not the %s template' % (ln, 'stub' if kind == 'stub' else 'stub or 404'))
            elif typ == 'module' and kind == 'noShell':
                if re.search(r'\\|/\*|//', text):
                    v.append('%d: an inline module script with a backslash or a comment (specifiers must be plain quoted strings)' % ln)
            else:
                v.append('%d: a <script type=%s>' % (ln, typ[:30]))
    return v


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
    if not (NEST_RE.fullmatch(text) or BARE_RE.fullmatch(text)):
        return False, 'its inline script is neither the nest_stubs.py template (slug only) nor a bare same-origin location.replace'
    gv = strict_grammar(pg, 'stub')  # C14 allowlist: the whole page, as a browser tokenizes it
    if gv:
        return False, 'it is outside the redirect-stub grammar (line %s)' % gv[0]
    return (True, 'nest stub') if NEST_RE.fullmatch(text) else (True, 'bare same-origin location.replace')


NONROOM_KEYS = ('domain', 'mode', 'topic', 'brand', 'doorway', 'govAgency')


def check_nonroom(room, name, site):
    """Hybrid site.json with mode doorway|parked (topics/site_mode.schema.json): no room, so no shell and no files.

    Such a dir must contain exactly one entry, a regular (non-symlink) site.json with only the hybrid keys. Any other
    file, any subdirectory (even empty, even .git or a dot-dir), any symlink, a "shell" block or an unknown mode is
    DRIFT (a doorway is an edge redirect and a parked domain serves nothing of ours)."""
    f, mode = [], site.get('mode')
    if mode not in ('doorway', 'parked'):
        f.append('site.json mode %r is not room, doorway or parked' % (mode,))
    extra = sorted(k for k in site if k not in NONROOM_KEYS)
    if extra:
        f.append('a %s site.json carries only %s, not %s' % (mode, '/'.join(NONROOM_KEYS), ', '.join(extra)))
    if 'govAgency' in site and (site['govAgency'] is not True or mode != 'doorway'):
        f.append('govAgency must be true and only on a doorway')
    if os.path.islink(os.path.normpath(room)):
        f.append('a %s dir may not be a symlink' % mode)
    try:
        names = sorted(os.listdir(room))
    except OSError as e:
        names = []
        f.append('dir unreadable: %s' % e)
    others = [x for x in names if x != 'site.json']
    if others:
        f.append('a %s domain serves no files of its own; the dir must contain exactly site.json, not %s'
                 % (mode, ', '.join(others[:5])))
    sj = os.path.join(room, 'site.json')
    if os.path.islink(sj) or not os.path.isfile(sj):
        f.append('site.json must be a regular file, not a symlink')
    return {'room': name, 'status': 'DRIFT' if f else 'OK', 'findings': f, 'warnings': [],
            'layers': {'mode': mode if isinstance(mode, str) else None}}


def check(room, mans, legacy=None):
    name = os.path.basename(os.path.normpath(room))
    try:
        site = json.load(open(os.path.join(room, 'site.json')))
    except Exception as e:
        return {'room': name, 'status': 'DRIFT', 'findings': ['site.json unreadable: %s' % e], 'warnings': [], 'layers': {}}
    if not isinstance(site, dict):
        return {'room': name, 'status': 'DRIFT', 'findings': ['site.json must be a JSON object, not %s' % type(site).__name__],
                'warnings': [], 'layers': {}}
    if 'mode' in site and site.get('mode') != 'room':
        return check_nonroom(room, name, site)
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
    # CSP rule: born strict. cspRequired defaults to true; only rooms on tools/csp_legacy_rooms.json may run without a
    # strict CSP (WARN) until their migration PR sets it true and takes them off the list
    site_id = site.get('siteId')
    legacy_set = load_csp_legacy() if legacy is None else legacy
    is_legacy = isinstance(site_id, str) and site_id in legacy_set
    req_top, req_sh = site.get('cspRequired'), sh.get('cspRequired')
    if req_top is not None and req_sh is not None and req_top != req_sh:
        f.append('CSP rule: site.json cspRequired (%r) and shell.cspRequired (%r) disagree' % (req_top, req_sh))
    req = req_sh if req_sh is not None else req_top
    if req is not None and not isinstance(req, bool):
        f.append('CSP rule: cspRequired must be true or false, not %r' % (req,))
        req = True
    if req is False and not is_legacy:
        f.append('CSP rule: cspRequired:false is allowed only for rooms on tools/csp_legacy_rooms.json (siteId %r is not '
                 'on it): every new room, the hub, topic mode and new domains start with a strict CSP' % (site_id,))
    csp_soft = is_legacy and req is not True  # legacy rooms: WARN; explicit cspRequired:true enforces (DRIFT)
    layers['csp'] = 'legacy (WARN)' if csp_soft else 'required'
    if sh.get('importmap') is not None and not isinstance(sh.get('importmap'), bool):
        f.append('shell.importmap must be true or false')
    if sh.get('recaptcha') is not None and not isinstance(sh.get('recaptcha'), bool):
        f.append('CSP rule: shell.recaptcha must be true or false')
    recaptcha = sh.get('recaptcha') is True
    if sh.get('googleSignIn') is not None and not isinstance(sh.get('googleSignIn'), bool):
        f.append('CSP rule: shell.googleSignIn must be true or false')
    google_signin = sh.get('googleSignIn') is True
    f.extend(hosting_redirects(room))  # C3
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
    good = set()
    for x in redirects:
        n = posixpath.normpath(x.lstrip('/')) if x.strip('/') else ''
        if (not n or re.search(r'[\x00-\x20\\%]', x) or REMOTE_RE.match(x) or x.startswith('//')
                or '..' in x.split('/') or n == '..' or n.startswith(('../', '/'))):
            f.append('shell.redirects entry %r is not a page path inside the room (no .., backslash, %%-encoding, '
                     'scheme or leading //)' % x)
        else:
            good.add(n)
    redirects = good
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
            ns_decl.append((page, where, decl, text))
            f.extend(injection_findings(text, where + ' ' + kind, bool(decl.get('injects'))))
        fb = FIREBASE_SDK_RE.search(text)
        if fb:  # C15: a Firebase-host import (static or dynamic) loads the Firebase SDK
            needs.setdefault(page, 'Firebase SDK')
            ns_add(page, where, 'Firebase SDK (%s names %s)' % (kind, fb.group(0)), False)
        return decl

    all_pages, page_objs, ns_preload, emoji_tags = [], {}, [], []
    for page, pg in pages(room):
        all_pages.append(page)
        page_objs[page] = pg
        # B8-B10: markup that html.parser and a browser tokenize differently is DRIFT on every page
        for msg in prescan(pg.raw, pg.toks, pg):
            f.append('%s:%s' % (page, msg))
        for msg in pg.enc:  # N1
            f.append('%s has %s: a page must be UTF-8 with no NUL bytes' % (page, msg))
        for msg in charset_findings(pg.raw, pg.toks):
            f.append('%s:%s' % (page, msg))
        if page.lower().endswith(XML_EXTS):  # N2
            for msg in xml_findings(pg.raw, pg.toks):
                f.append('%s:%s' % (page, msg))
        is_stub, stub_why = redirect_stub(pg)
        is_stub = is_stub and page != 'index.html'  # the main page is never a stub, whatever it contains
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
                ns_preload.append((page, '%s:%d' % (page, ln['line']), ' '.join(rel_), href))
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
            if typ == 'importmap':  # N6: an import map remaps every module specifier on the page, pinned ones included
                ns_add(page, where, '<script type=importmap>', False)
                if src is not None:
                    f.append('%s <script type=importmap src=...>: external import maps are not allowed' % where)
                elif sh.get('importmap') is not True:
                    f.append('%s <script type=importmap>: an import map can remap module specifiers; not allowed unless '
                             'shell.importmap is true (default false)' % where)
                else:
                    try:
                        im = json.loads(s['text'])
                        tgts = list((im.get('imports') or {}).values()) + [v for sc in (im.get('scopes') or {}).values()
                                                                            for v in (sc or {}).values()]
                    except Exception:
                        tgts = None
                    if tgts is None or not all(isinstance(x, str) for x in tgts):
                        f.append('%s <script type=importmap> is not a JSON {imports, scopes} map' % where)
                    else:
                        for x in tgts:
                            if REMOTE_RE.match(norm_js(x)) or norm_js(x).startswith('//'):
                                f.append('%s import map points a specifier at remote %s' % (where, x[:60]))
                    code_block(page, where, s['text'], 'import map')
                continue
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
            if FIREBASE_RE.fullmatch(src):
                needs.setdefault(page, 'Firebase SDK')  # C12
                ns_add(page, where, 'Firebase SDK', False)
                continue
            em = EMOJI_RE.fullmatch(src)
            if em:
                ns_add(page, where, 'remote script %s' % src, False)
                emoji_tags.append((page, where, em.group(1), bool(a.get('integrity'))))  # decided after the CSP rule
                continue
            bare = re.split(r'[?#]', src, maxsplit=1)[0]
            if bare != src and (PIN_RE.fullmatch(bare) or PRE_RE.fullmatch(bare)):
                f.append('%s pin URL carries a query or fragment (%s): pins must be the bare pinned URL, no ?v=' % (where, src[len(bare):][:40]))
                continue
            m = PIN_RE.fullmatch(src)
            pre = PRE_RE.fullmatch(src)
            if m or (pre and man and pre.group(1) == man.get('sourceCommit')):
                ver, fn = (m.group(2), m.group(3)) if m else (base, pre.group(2))
                if typ == 'module':
                    f.append('%s %s pin has type=module: document.currentScript is null there, so the shell ignores data-site '
                             '(and runs deferred); use a classic <script>' % (where, fn))
                    continue
                pf = pin_form(pg, s)  # N3: strict pin form, as a browser builds the page
                if pf:
                    f.append('%s %s pin is not live: %s' % (where, fn, '; '.join(pf)))
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
            if 'emoji-picker-element' in rel and not a.get('integrity'):  # self-hosted emoji: 'self' file with SRI
                w.append('%s self-hosted %s has no integrity (SRI) attribute' % (where, rel))
            if fork and rel == fork_file:
                pf = pin_form(pg, s)
                if pf:
                    f.append('%s fork file tag is not live: %s' % (where, '; '.join(pf)))
                elif runs and typ != 'module':
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
            if '\\' in spec:  # B11: in JS a backslash is a string escape, not a path separator
                f.append('%s imports %r: a module specifier with a backslash (an escape the JS parser decodes first)'
                         % (where, spec[:60]))
                continue
            raw_spec, spec = spec, norm_js(spec)
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
        text, enc_ = decode_utf8(open(p, 'rb').read())
        for msg in enc_:  # N1
            f.append('%s has %s: room JS must be UTF-8 with no NUL bytes' % (rel, msg))
        if rel in ns_keep:  # N5: no string-to-code on a noShell page, declared "injects" or not
            for m_ in NS_EVAL_RE.finditer(text):
                f.append('%s is loaded on noShell page %s and evaluates a string as code (%s): not allowed on a noShell '
                         'page' % (rel, ns_keep[rel], m_.group(0)[:30]))
        f.extend(injection_findings(text, rel, bool(decl.get('injects'))))
        if rel in ns_keep and decl.get('injects'):  # B13
            f.append('%s is loaded on noShell page %s but declares "injects" (%s): code on a noShell page may not inject '
                     'or evaluate code' % (rel, ns_keep[rel], str(decl['injects'])[:40]))
        if rel in ns_keep and import_specs(text):
            f.append('%s is loaded on noShell page %s but imports modules (a noShell page may run only keep files and '
                     'declared inline code)' % (rel, ns_keep[rel]))
        if rel in ns_keep and FIREBASE_SDK_RE.search(text):
            f.append('%s is loaded on noShell page %s and names the Firebase SDK (%s): a noShell page may not load '
                     'Firebase' % (rel, ns_keep[rel], FIREBASE_SDK_RE.search(text).group(0)))
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
        if pg_ in page_objs:  # C15 allowlist grammar
            for v_ in strict_grammar(page_objs[pg_], 'noShell'):
                f.append('%s:%s on a noShell page (outside the noShell grammar)' % (pg_, v_))
        for page_, where, rel_, href in ns_preload:
            if page_ == pg_:
                f.append('%s noShell page has remote <link rel=%s href=%s>' % (where, rel_, href))
        for where, what, ok in ns_items.get(pg_, []):
            if not ok:
                f.append('%s noShell page loads %s: a noShell page may load only keep files%s and declared inline code'
                         % (where, what, ' flagged noShellOk' if ns_flag else ''))
        # C15: declared inline code on a noShell page may not inject code or import remote modules
        for page_, where, decl, text_ in ns_decl:
            if page_ != pg_:
                continue
            for m_ in NS_EVAL_RE.finditer(text_):  # N5
                f.append('%s noShell page inline code evaluates a string as code (%s): not allowed on a noShell page'
                         % (where, m_.group(0)[:30]))
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
    # CSP rule: every HTML page needs a strict CSP that applies to it (meta in <head>, or a hosting header rule)
    room_hashes = set()  # hashes a strict CSP may list: inline scripts of redirect stubs and 404.html only
    for p_, pg_ in page_objs.items():
        if p_ not in stubs and os.path.basename(p_).lower() != '404.html':
            continue
        for s_ in pg_.out:
            if s_['attrs'].get('src') is None and s_['text'].strip():
                room_hashes |= script_hash_sources(s_['text'])
    pin_pages = {p_ for p_, pg_ in page_objs.items()
                 if any(PIN_RE.fullmatch(norm_url(s_['attrs'].get('src'))) for s_ in pg_.out)}
    room_pin_dirs = pin_dirs_of(page_objs['index.html']) if 'index.html' in page_objs else set()
    missing, weak, strict_pols, hdr_bad = [], {}, {}, {}
    csp_pages = [p_ for p_ in all_pages if p_.lower().endswith(CSP_PAGE_EXTS)]
    for page in csp_pages:
        pg = page_objs[page]
        pols = [(pol, bad) for ln_, mp, bad in meta_csps(pg) for pol in (mp or [{}])]
        for ln_, mp, bad in meta_csps(pg):
            if bad and bad.startswith(('the CSP value has character', 'the CSP has an invalid directive name')):
                hdr_bad.setdefault('%s:%d <meta> CSP: %s' % (page, ln_, bad), None)
        dirs = pin_dirs_of(pg) or room_pin_dirs
        for fn_, pat, rx, val in hdr_rules:
            if rx is None or any(rx.match(u) for u in page_urls(page)):
                sb = csp_syntax_bad(val)
                if sb:
                    hdr_bad.setdefault('%s header CSP for %s: %s' % (fn_, pat, sb), None)
                pols += [(pol, sb) for pol in csp_policies(val)]
        if not pols:
            missing.append(page)
            continue
        good, reasons = [], []
        for pol, bad in pols:
            why = [bad] if bad else csp_weak(pol, room_hashes, page in pin_pages, dirs, recaptcha, google_signin)
            (reasons.extend(why) if why else good.append(pol))
        if good:
            strict_pols[page] = good
            listed = {x for pol in good for d_ in ('script-src', 'default-src', 'script-src-elem') for x in pol.get(d_) or []}
            for s_ in pg.out:
                if s_['attrs'].get('src') is None and s_['text'].strip() and \
                        (s_['attrs'].get('type') or '').strip().lower() not in DATA_TYPES and not (script_hash_sources(s_['text']) & listed):
                    w.append('CSP rule: %s:%d inline <script> hash is not in the CSP: the strict CSP will block it' % (page, s_['line']))
            for c_ in pg.code:
                w.append('CSP rule: %s:%d %s: a strict CSP blocks inline handlers and javascript: URLs' % (page, c_['line'], c_['kind']))
        else:
            weak.setdefault('; '.join(dict.fromkeys(reasons)), []).append(page)

    def _pl(xs):
        return ', '.join(xs[:8]) + (', ... (%d more)' % (len(xs) - 8) if len(xs) > 8 else '')
    csp_msgs = []
    if missing:
        csp_msgs.append('no Content-Security-Policy on %d of %d pages (%s): add the shell/csp.md meta tag or a hosting '
                        'header CSP' % (len(missing), len(csp_pages), _pl(missing)))
    for why, pgs in sorted(weak.items()):
        csp_msgs.append('CSP is not strict on %s: %s' % (_pl(pgs), why))
    csp_msgs.extend(hdr_bad)  # B1: a malformed header value is drift even when another policy on the page is strict
    for m_ in csp_msgs:
        if csp_soft:
            w.append('CSP rule (legacy room on tools/csp_legacy_rooms.json, WARN until its migration PR): ' + m_)
        else:
            f.append('CSP rule: ' + m_)
    # emoji-picker-element from jsDelivr: only at an exact version whose folder a strict CSP on the page lists
    # (index.js imports ./picker.js and ./database.js, which SRI on the tag cannot cover); the other accepted form is
    # a self-hosted 'self' copy with integrity (checked where local scripts are read)
    for page, where, ver, has_sri in emoji_tags:
        pinned_by_csp = EXACT_VER.fullmatch(ver) and any(
            EMOJI_SRC_RE.fullmatch(x) and EMOJI_SRC_RE.fullmatch(x).group(1) == ver and x.endswith('@%s/' % ver)
            for pol in strict_pols.get(page, []) for d_ in ('script-src', 'default-src', 'script-src-elem') for x in pol.get(d_) or [])
        if not pinned_by_csp:
            w.append('%s emoji-picker-element@%s has no SRI pin: load it from an exact-version folder listed in a strict '
                     'script-src, or self-host it with integrity (shell/csp.md)' % (where, ver))
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
        pinned = any(PIN_RE.fullmatch(norm_url((s.get('attrs') or {}).get('src'))) for s in pg.out)
        if page != 'index.html' and not pinned and (pg.code or any(
                (s['attrs'].get('src') and (not REMOTE_RE.match(norm_url(s['attrs']['src']))
                                            or FIREBASE_RE.fullmatch(norm_url(s['attrs']['src']))))
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
    ap.add_argument('--csp-legacy', default=CSP_LEGACY_FILE,
                    help='legacy-room list for the CSP rule (default tools/csp_legacy_rooms.json)')
    a = ap.parse_args()
    if a.suggest:
        print(json.dumps({os.path.basename(os.path.normpath(r)): suggest(r) for r in a.rooms}, indent=2))
        return
    mans = manifests(a.shell_root)
    legacy = load_csp_legacy(a.csp_legacy)
    res = [check(r, mans, legacy) for r in a.rooms]
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
