#!/usr/bin/env python3
"""Render the hub (hub/src -> hub/site) from brand/brand.json. Python stdlib only.

brand/brand.json is the ONE place a brand string lives. Templates in hub/src/templates and hub/src/partials never
spell the brand; they use tokens:

  {{brand.KEY}} / {{brand.KEY.SUB}}   a brand.json value (values may hold tokens too, e.g. footer -> {{year}})
  {{year}}                            year of hub/src/data/highlights.json "generated" (deterministic, not the clock)
  {{shell.pinUrl}} {{shell.integrity}} {{shell.csp}}   the shared shell, self-hosted at /shell/<base>/factory.js (hub/src/config.json);
                                                       shell.csp is CSP_AUTH on shell pages, CSP_STATIC on noShell pages
  {{shell.firebaseVersion}}                            the exact Firebase compat SDK version the shell page loads
  {{page.title}} {{page.description}}  per-page values from hub/src/config.json "pages"
  {{asset:/path}}                     /path?v=<sha256[:10] of the rendered file> (cache-bust, rendered first)
  {{> name}}                          hub/src/partials/name.html
  {{footer:links}}                    brand.footer with Terms / Privacy / Report / the takedown email linked
  {{url:brand.KEY}}                   a brand value percent-encoded for a URL (mailto subject, ...)

Values are HTML-escaped in .html/.svg files and JSON-string-escaped in .json/.js files (.css/.txt: as is). An unknown token, a missing key or a token
left in the output is an error, so a rename cannot silently leave a gap.

Vendored files (hub/src/config.json "vendor": shared factory assets such as assets/whomark/*) are copied from the
repo. Their upstream text was authored under UPSTREAM below; when brand.json differs, the renderer swaps those
strings for the brand.json values, so with today's brand the copies stay byte-identical to the shared files.

The template "topics.html" renders to <topicPathPrefix>index.html, so the topic index follows a path rename.
Topic pages: every row of the seed named by config.json "topics.seed" (topics/seed_wave1.json) except HOLD rows renders
hub/src/topic-template.html to <topicPathPrefix><slug>/index.html (listed in shell.noShell). <!--if:NAME--> blocks in
that template are kept or dropped per topic (status, profile, optional copy) and the markers never reach the output.
A topic row with govNonAffiliation true (topics/seed_wave2_agency.json) shows brand.nonAffiliationGov under the title
(if:gov) and as a line inside the footer.
Robots: "topics.hubNoindex" true = every page noindex,nofollow and an empty sitemap (the pre-launch lock, kept as the rollback switch). When it is false, a hub page
is index,follow unless its config.json "pages" entry sets "robots" (404 and the topic index keep noindex,nofollow), and
every topic page follows its own status (tools/topic_status.py: only "active" is indexable; hidden, eligible, quiet and
archived stay noindex,nofollow). sitemap.xml lists the indexable hub pages and the sitemap-eligible topics, nothing else.
Every page carries <link rel="canonical"> on https://<brand.primaryDomain>, so the *.web.app hosts never compete with it.
shell.keep sha256 values in site.json are filled from the rendered files.

Usage: python3 tools/brand_render.py [--check] [--brand PATH] [--out DIR] [--src DIR]
  --check  render to a temp dir and fail (exit 1) if hub/site differs (names every differing file)
"""
import argparse, base64, filecmp, hashlib, json, os, re, sys, tempfile, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import topic_slug, topic_status  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# hub fork of the shared shell (EXCEPTIONS.md E21): the one header line that names the source repo is replaced
FORK_HEADER_FROM = b'github.com/jebbdykstra99/subx-factory'
FORK_HEADER = ' * Source: SubX shared shell %s (hub fork, header only)'
# Strings the shared upstream files (assets/whomark/*) were written with. Not hub copy: only used to re-brand
# vendored bytes; most specific first.
UPSTREAM = [('legalEntity', 'Sub' + 'X, LLC'), ('takedownEmail', 'takedown@sub' + 'x.it'),
            ('primaryDomain', 'sub' + 'x.it'), ('shortName', 'Sub' + 'X')]
TOKEN_RE = re.compile(r'\{\{\s*([^{}]*?)\s*\}\}')
KEY_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)*$')
TEXT_EXT = ('.html', '.json', '.js', '.css', '.txt', '.svg')


class RenderError(Exception):
    pass


def sha256_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def lookup(ctx, key):
    cur = ctx
    for part in key.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            raise RenderError('unknown token {{%s}}' % key)
        cur = cur[part]
    if isinstance(cur, (dict, list)):
        raise RenderError('token {{%s}} is not a string' % key)
    return str(cur)


def expand(text, ctx, depth=0):
    """Resolve {{brand.*}} / {{year}} tokens inside a brand value (no escaping: raw text)."""
    if depth > 5:
        raise RenderError('token nesting too deep in %r' % text[:60])
    def rep(m):
        k = m.group(1)
        if not KEY_RE.fullmatch(k):
            raise RenderError('bad token inside a brand value: {{%s}}' % k)
        return expand(lookup(ctx, k), ctx, depth + 1)
    return TOKEN_RE.sub(rep, text)


def html_attr(s):
    """Escape for HTML text and double-quoted attributes (every template attribute uses double quotes, so ' stays
    literal: a CSP like script-src 'self' reads the same to browsers and to tools/shell_drift.py)."""
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def esc_for(ext):
    if ext == '.html' or ext == '.svg':
        return html_attr
    if ext in ('.json', '.js'):
        return lambda s: json.dumps(s, ensure_ascii=False)[1:-1]
    return lambda s: s


def footer_links(ctx):
    """brand.footer, escaped, with its Terms / Privacy / Report words and the takedown email turned into links."""
    text = html_attr(expand(lookup(ctx, 'brand.footer'), ctx))
    mail = html_attr(lookup(ctx, 'brand.takedownEmail'))
    for word, href in (('Terms', '/terms.html'), ('Privacy', '/privacy.html'), ('Report', '/report.html')):
        text = re.sub(r'\b%s\b' % word, '<a href="%s">%s</a>' % (href, word), text, count=1)
    if mail in text:
        text = text.replace(mail, '<a data-takedown href="mailto:%s">%s</a>' % (mail, mail), 1)
    return text


# HUB SIGN-IN (2026-11-04). Static (noShell) pages: self only. The shell page (index.html) adds exactly what the
# shell's sign-in needs: the Firebase compat SDK at one exact version, reCAPTCHA v3 for App Check (shell.recaptcha),
# Google's sign-in helper (gapi: api.js plus the gapi_iframes module it loads from /_/scs/abc-static/, needed by
# signInWithPopup / signInWithRedirect), the shell's web-config fetch, the Auth / Firestore / App Check APIs, and the
# reCAPTCHA v3 score call (connect to www.google.com/recaptcha/). Found by headless Chrome CSP-violation capture.
FIREBASE_VERSION = '10.12.2'
CSP_STATIC = "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; font-src 'self'"
CSP_AUTH_SCRIPT = ["'self'", 'https://www.gstatic.com/firebasejs/%s/' % FIREBASE_VERSION,
                   'https://www.google.com/recaptcha/api.js', 'https://www.gstatic.com/recaptcha/releases/',
                   'https://apis.google.com/js/api.js', 'https://apis.google.com/_/scs/abc-static/']
CSP_AUTH_CONNECT = ["'self'", 'https://subx-skins.web.app', 'https://identitytoolkit.googleapis.com',
                    'https://securetoken.googleapis.com', 'https://firestore.googleapis.com',
                    'https://content-firebaseappcheck.googleapis.com', 'https://www.google.com/recaptcha/']
CSP_AUTH_FRAME = ['https://subx-skins.firebaseapp.com', 'https://www.google.com/recaptcha/']
CSP_AUTH = '; '.join(['script-src ' + ' '.join(CSP_AUTH_SCRIPT), 'connect-src ' + ' '.join(CSP_AUTH_CONNECT),
                      'frame-src ' + ' '.join(CSP_AUTH_FRAME), "object-src 'none'", "base-uri 'none'", "font-src 'self'"])


class Renderer:
    def __init__(self, src, brand_path, out):
        self.src, self.out = src, out
        self.cfg = json.load(open(os.path.join(src, 'config.json'), encoding='utf-8'))
        brand = json.load(open(brand_path, encoding='utf-8'))
        hl = json.load(open(os.path.join(src, 'data', 'highlights.json'), encoding='utf-8'))
        year = str(hl.get('generated', ''))[:4]
        if not re.fullmatch(r'^\d{4}$', year):
            raise RenderError('hub/src/data/highlights.json has no "generated" year')
        sh = self.cfg['shell']
        # B2 (2026-11-04): the pinned shell is self-hosted at /shell/<base>/factory.js as a hub-only fork (EXCEPTIONS.md E21):
        # the pinned bytes with ONLY the header source line replaced, under a new SRI. script-src and connect-src are 'self'
        # only, so the hub makes no external request and no CDN or repo path appears in the output. shell_bytes() builds it.
        self.shell_rel = 'shell/%s/factory.js' % sh['base']
        pin = '/' + self.shell_rel
        self.shell_data, self.shell_sha, self.shell_sri = self.shell_bytes()
        csp = CSP_STATIC
        # HUB SIGN-IN (2026-11-04): pages that run the shell (index.html) get CSP_AUTH, the exact Firebase Auth +
        # Firestore + App Check origins the shell's sign-in needs; every noShell static page keeps the strict policy.
        for c in (CSP_STATIC, CSP_AUTH):
            if re.search(r'[^\x20-\x7e]|,', c):
                raise RenderError('CSP must be printable ASCII without commas')
        self.csp_auth = CSP_AUTH
        self.ctx = {'brand': brand, 'year': year,
                    'shell': {'pinUrl': pin, 'integrity': self.shell_sri, 'csp': csp, 'base': sh['base'],
                              'firebaseVersion': FIREBASE_VERSION}}
        prefix = brand.get('topicPathPrefix', '')
        if not re.fullmatch(r'^/[a-z0-9][a-z0-9-]*/$', prefix):
            raise RenderError('brand.topicPathPrefix must look like /t/ (got %r)' % prefix)
        self.topic_dir = prefix.strip('/')
        self.assets = {}
        self.written = set()

    # ---- token rendering ----
    def render_text(self, text, ext, page=None, where='?', extra=None):
        esc = esc_for(ext)
        def partial(m):
            name = m.group(1)
            p = os.path.join(self.src, 'partials', name + '.html')
            if not re.fullmatch(r'^[a-z0-9-]+$', name) or not os.path.isfile(p):
                raise RenderError('%s: unknown partial {{> %s}}' % (where, name))
            return open(p, encoding='utf-8').read().rstrip('\n')
        for _ in range(3):
            text = re.sub(r'\{\{>\s*([^{}\s]+)\s*\}\}', partial, text)
        ctx = dict(self.ctx, page=page or {}, **(extra or {}))

        def rep(m):
            k = m.group(1)
            if k.startswith('asset:'):
                path = k[6:]
                if path not in self.assets:
                    raise RenderError('%s: {{%s}} names no rendered asset' % (where, k))
                return path + '?v=' + self.assets[path]
            if k == 'footer:links':
                return footer_links(ctx)
            if k.startswith('url:'):
                if not KEY_RE.fullmatch(k[4:]):
                    raise RenderError('%s: bad token {{%s}}' % (where, k))
                return urllib.parse.quote(expand(lookup(ctx, k[4:]), ctx), safe='')
            if not KEY_RE.fullmatch(k):
                raise RenderError('%s: bad token {{%s}}' % (where, k))
            if k.startswith('topic.'):
                # topic data is content: escaped, never token-expanded; braces become entities so text such as
                # "{{x}}" in a description shows as typed instead of tripping the leftover-token check
                return esc(lookup(ctx, k)).replace('{', '&#123;').replace('}', '&#125;')
            return esc(expand(lookup(ctx, k), ctx))
        try:
            out = TOKEN_RE.sub(rep, text)
        except RenderError as e:
            raise RenderError('%s: %s' % (where, e))
        if '{{' in out or '}}' in out:
            raise RenderError('%s: unrendered token left: %r' % (where, out[out.find('{{'):][:40]))
        return out

    def out_path(self, rel):
        if rel == 'topics.html':
            rel = self.topic_dir + '/index.html'
        return rel

    def write(self, rel, data):
        self.written.add(rel)
        p = os.path.join(self.out, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'wb') as fh:
            fh.write(data)
        return p

    def shell_bytes(self):
        """The self-hosted hub fork of shell/<base>/factory.js (never re-branded). The pinned file is verified first: its
        sha384 must equal config.json shell.integrity and SHELL.json, and its sha256 and size must equal SHELL.json, or the
        render stops. Then exactly one line changes: the header comment line naming the source repo becomes
        FORK_HEADER. Every other byte is identical. Returns (fork bytes, fork sha256, fork SRI sha384)."""
        sh = self.cfg['shell']
        man = json.load(open(os.path.join(ROOT, 'shell', sh['base'], 'SHELL.json'), encoding='utf-8'))['files']['factory.js']
        data = open(os.path.join(ROOT, 'shell', sh['base'], 'factory.js'), 'rb').read()
        sri = 'sha384-' + base64.b64encode(hashlib.sha384(data).digest()).decode()
        if not (sri == sh['integrity'] == man['integrity']):
            raise RenderError('shell/%s/factory.js sha384 %s != config.json shell.integrity / SHELL.json' % (sh['base'], sri))
        if hashlib.sha256(data).hexdigest() != man['sha256'] or len(data) != man['bytes']:
            raise RenderError('shell/%s/factory.js sha256/bytes != SHELL.json' % sh['base'])
        lines = data.split(b'\n')
        hits = [i for i, ln in enumerate(lines) if FORK_HEADER_FROM in ln]
        if len(hits) != 1 or not lines[hits[0]].lstrip().startswith(b'*'):
            raise RenderError('shell/%s/factory.js: expected exactly one header comment line with %r (found %d)'
                              % (sh['base'], FORK_HEADER_FROM.decode(), len(hits)))
        lines[hits[0]] = (FORK_HEADER % sh['base']).encode()
        fork = b'\n'.join(lines)
        fsri = 'sha384-' + base64.b64encode(hashlib.sha384(fork).digest()).decode()
        return fork, hashlib.sha256(fork).hexdigest(), fsri

    def rebrand_vendor(self, data):
        brand = self.ctx['brand']
        text = data.decode('utf-8')
        marks = []
        for i, (key, old) in enumerate(UPSTREAM):
            new = brand[key]
            if new == old:
                continue
            mark = '\x00%d\x00' % i
            text = text.replace(old, mark)
            marks.append((mark, new))
        for mark, new in marks:
            text = text.replace(mark, new)
        return text.encode('utf-8')

    def run(self):
        os.makedirs(self.out, exist_ok=True)
        cfg = self.cfg
        # 1. vendored shared files (byte copies, re-branded only when the brand differs)
        for v in cfg.get('vendor', []):
            data = open(os.path.join(ROOT, v['from']), 'rb').read()
            if v['to'].endswith(TEXT_EXT):
                data = self.rebrand_vendor(data)
            self.write(v['to'], data)
            self.assets['/' + v['to']] = hashlib.sha256(data).hexdigest()[:10]
        # 1b. the self-hosted shell (byte copy, no ?v= query: a pin URL may not carry one)
        self.write(self.shell_rel, self.shell_data)
        # 2. data files copied as is (room content, not brand copy)
        for d in cfg.get('data', []):
            data = open(os.path.join(self.src, 'data', d), 'rb').read()
            self.write(d, data)
            self.assets['/' + d] = hashlib.sha256(data).hexdigest()[:10]
        # 3. non-page templates (css, js, txt, svg), then site.json, then pages
        tdir = os.path.join(self.src, 'templates')
        names = sorted(n for n in os.listdir(tdir) if os.path.isfile(os.path.join(tdir, n)))
        pages = cfg['pages']
        for n in names:
            if n.endswith('.html') or n == 'site.json':
                continue
            ext = os.path.splitext(n)[1]
            text = self.render_text(open(os.path.join(tdir, n), encoding='utf-8').read(), ext, where=n)
            data = text.encode('utf-8')
            self.write(n, data)
            self.assets['/' + n] = hashlib.sha256(data).hexdigest()[:10]
        site = json.loads(self.render_text(open(os.path.join(tdir, 'site.json'), encoding='utf-8').read(), '.json',
                                           where='site.json'))
        # the self-hosted shell is a declared hub-only fork (header line only; shell_drift reports FORK with 2 diff lines), E21
        site.setdefault('shell', {}).update({'fork': True, 'file': self.shell_rel, 'sha256': self.shell_sha,
                                             'reason': 'Self-hosted hub fork of shell/%s/factory.js: header source line only, new SRI; static pages are self only, the shell page adds only the Firebase Auth origins' % self.cfg['shell']['base'],
                                             'exception': 'E21'})
        for k in site.get('shell', {}).get('keep', []):
            p = os.path.join(self.out, k['file'])
            if not os.path.isfile(p):
                raise RenderError('site.json shell.keep %s was not rendered' % k['file'])
            k['sha256'] = sha256_file(p)
        topics = self.topics()
        ns = site.setdefault('shell', {}).setdefault('noShell', [])
        ns += [self.topic_path(t['slug']) for t in topics]
        rail = os.path.join(self.src, 'data', 'rail.json')
        if os.path.isfile(rail):
            site.setdefault('rail', {})['outbound'] = json.load(open(rail, encoding='utf-8'))
        data = (json.dumps(site, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
        self.write('site.json', data)
        self.assets['/site.json'] = hashlib.sha256(data).hexdigest()[:10]
        missing = [n for n in names if n.endswith('.html') and n not in pages]
        if missing:
            raise RenderError('templates without a "pages" entry in config.json: %s' % ', '.join(missing))
        shell_noshell = set(x.lstrip('/') for x in site.get('shell', {}).get('noShell', []))
        hub_noindex = self.topic_cfg()['hubNoindex']
        self.indexable_pages = []
        for n, meta in sorted(pages.items()):
            page = {k: expand(v, self.ctx) if isinstance(v, str) else v for k, v in meta.items() if not k.startswith('_')}
            if hub_noindex:
                page['robots'] = topic_status.NOINDEX
            page.setdefault('robots', topic_status.INDEX)
            if page['robots'] not in (topic_status.INDEX, topic_status.NOINDEX):
                raise RenderError('config.json pages.%s.robots must be %r or %r' % (n, topic_status.INDEX, topic_status.NOINDEX))
            page['canonical'] = self.canonical(self.out_path(n))
            if page['robots'] == topic_status.INDEX:
                self.indexable_pages.append(page['canonical'])
            extra = None
            if self.out_path(n) not in shell_noshell:
                extra = {'shell': dict(self.ctx['shell'], csp=self.csp_auth)}
            text = self.render_text(open(os.path.join(tdir, n), encoding='utf-8').read(), '.html', page, where=n, extra=extra)
            self.write(self.out_path(n), text.encode('utf-8'))
        # 4. topic pages (non-HOLD seed rows) and the sitemap (eligible topics only)
        for t in topics:
            self.write(self.topic_path(t['slug']), self.render_topic(t).encode('utf-8'))
        self.write('sitemap.xml', self.sitemap(topics).encode('utf-8'))
        return self

    # ---- topics ----
    def topic_cfg(self):
        return dict({'seed': None, 'open': False, 'showDoorways': False, 'hubNoindex': True}, **self.cfg.get('topics', {}))

    def canonical(self, rel):
        """https://<primaryDomain>/<rel>, with a trailing index.html dropped (index.html -> /, t/x/index.html -> /t/x/)."""
        if rel == 'index.html' or rel.endswith('/index.html'):
            rel = rel[:-len('index.html')]
        return 'https://%s/%s' % (self.ctx['brand']['primaryDomain'], rel)

    def topic_path(self, slug):
        return '%s/%s/index.html' % (self.topic_dir, slug)

    def topics(self):
        tc = self.topic_cfg()
        if not tc['seed']:
            return []
        seed = json.load(open(os.path.join(ROOT, tc['seed']), encoding='utf-8'))
        words = topic_slug.reserved(self.ctx['brand'])
        out, seen = [], set()
        for t in seed['topics']:
            e = topic_slug.errors(t['slug'], words=words)
            if e or t['slug'] in seen:
                raise RenderError('seed topic %s refused: %s' % (t['slug'], '; '.join(e) or 'duplicate'))
            seen.add(t['slug'])
            if topic_status.rendered(t['status']):
                out.append(t)
        return out

    def sitemap(self, topics):
        b = self.ctx['brand']
        hub_noindex = self.topic_cfg()['hubNoindex']
        locs = [] if hub_noindex else list(getattr(self, 'indexable_pages', []))
        locs += ['https://%s%s%s/' % (b['primaryDomain'], b['topicPathPrefix'], t['slug'])
                 for t in topics if topic_status.sitemap_eligible(t['status'], hub_noindex)]
        body = ''.join('  <url><loc>%s</loc></url>\n' % html_attr(u) for u in locs)
        return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s</urlset>\n' % body

    def render_topic(self, topic):
        """Render hub/src/topic-template.html for one topic (a seed row with title, or a dict with name) per HUB_COPY
        4a-4e and ACTIVITY_RULE: <!--if:NAME--> blocks are kept or dropped here, so the page carries only its own
        state and no HTML comments. Optional copy (longDescription, goodPosts, offTopic, rulesShort, legacyDomain) is
        left out when empty. Call after the assets are rendered (run() does)."""
        topic = dict(topic)
        topic.setdefault('name', topic.get('title', ''))
        topic.setdefault('status', 'hidden')
        miss = [k for k in ('slug', 'name', 'description') if not str(topic.get(k, '')).strip()]
        if miss:
            raise RenderError('topic is missing %s' % ', '.join(miss))
        e = topic_slug.errors(topic['slug'], brand=self.ctx['brand'])
        if e:
            raise RenderError('; '.join(e))
        if not topic_status.rendered(topic['status']):
            raise RenderError('topic %s is on HOLD and is never rendered' % topic['slug'])
        tc = self.topic_cfg()
        st, prof = topic['status'], topic.get('legalProfile', 'standard-18')
        doors = topic.get('doorwayDomains') or []
        topic.setdefault('legacyDomain', doors[0] if doors else '')
        has = lambda k: bool(str(topic.get(k) or '').strip())
        cond = {'doorway': tc['showDoorways'] and has('legacyDomain'),
                'not-live': st in ('hidden', 'eligible') and not tc['open'],
                'state-hidden': st in ('hidden', 'eligible') and tc['open'],
                'state-archived': st == 'archived', 'state-quiet': st == 'quiet',
                'state-active-new': st == 'active' and bool(topic.get('justActivated')),
                'about': has('longDescription'), 'goodPosts': has('goodPosts'), 'offTopic': has('offTopic'),
                'rulesShort': has('rulesShort'), 'rules-default': not has('rulesShort'),
                'profile-not-advice': prof in ('sensitive-18', 'alcohol-21'), 'profile-21': prof == 'alcohol-21',
                'gov': topic.get('govNonAffiliation') is True}
        if cond['gov'] and not str(self.ctx['brand'].get('nonAffiliationGov') or '').strip():
            raise RenderError('topic %s: govNonAffiliation needs brand.nonAffiliationGov' % topic['slug'])
        text = open(os.path.join(self.src, 'topic-template.html'), encoding='utf-8').read()
        block = re.compile(r'<!--if:([A-Za-z0-9-]+)-->\n(.*?)<!--/if:\1-->\n', re.S)
        for _ in range(5):
            def keep(m):
                if m.group(1) not in cond:
                    raise RenderError('topic-template.html: unknown block if:%s' % m.group(1))
                return m.group(2) if cond[m.group(1)] else ''
            text = block.sub(keep, text)
        if '<!--' in text:
            raise RenderError('topic-template.html: unbalanced <!--if:--> block or stray comment')
        page = {'title': topic['name'] + ' · ' + self.ctx['brand']['name'], 'description': topic['description'],
                'robots': topic_status.robots(st, tc['hubNoindex']), 'canonical': self.canonical(self.topic_path(topic['slug']))}
        gov = cond['gov']
        topic = {k: v for k, v in topic.items() if isinstance(v, str)}
        out = self.render_text(text, '.html', page, where='topic-template.html', extra={'topic': topic})
        if gov:
            # the shared footer partial has no per-topic blocks; add the line inside this page's footer
            end = out.rfind('</footer>')
            if end < 0:
                raise RenderError('topic-template.html: govNonAffiliation needs the footer partial')
            line = '  <span class="legal-footer-line legal-footer-gov">%s</span>\n' % esc_for('.html')(self.ctx['brand']['nonAffiliationGov'])
            out = out[:end] + line + out[end:]
        return out


def files_under(d):
    out = set()
    for base, _, fs in os.walk(d):
        for f in fs:
            out.add(os.path.relpath(os.path.join(base, f), d).replace(os.sep, '/'))
    return out


def render(src=None, brand=None, out=None):
    src = src or os.path.join(ROOT, 'hub', 'src')
    brand = brand or os.path.join(ROOT, 'brand', 'brand.json')
    out = out or os.path.join(ROOT, 'hub', 'site')
    return Renderer(src, brand, out).run()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--brand')
    ap.add_argument('--src')
    ap.add_argument('--out')
    a = ap.parse_args(argv)
    target = a.out or os.path.join(ROOT, 'hub', 'site')
    try:
        if a.check:
            with tempfile.TemporaryDirectory() as tmp:
                render(a.src, a.brand, tmp)
                want, have = files_under(tmp), files_under(target) if os.path.isdir(target) else set()
                bad = sorted((want ^ have) | {f for f in want & have
                                              if not filecmp.cmp(os.path.join(tmp, f), os.path.join(target, f), shallow=False)})
                if bad:
                    print('brand_render --check: hub/site is stale; run python3 tools/brand_render.py. Differs: '
                          + ', '.join(bad))
                    return 1
                print('brand_render --check: hub/site matches brand/brand.json + hub/src (%d files)' % len(want))
                return 0
        # rebuild in place: only files the renderer owns are rewritten; stray files are reported, never deleted
        r = render(a.src, a.brand, target)
        extra = files_under(target) - r.written
        if extra:
            print('note: files in %s the renderer does not produce (left alone): %s' % (target, ', '.join(sorted(extra))))
        print('rendered %s' % os.path.relpath(target, os.getcwd()))
        return 0
    except RenderError as e:
        print('brand_render: %s' % e, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
