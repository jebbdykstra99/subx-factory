#!/usr/bin/env python3
"""Render the hub (hub/src -> hub/site) from brand/brand.json. Python stdlib only.

brand/brand.json is the ONE place a brand string lives. Templates in hub/src/templates and hub/src/partials never
spell the brand; they use tokens:

  {{brand.KEY}} / {{brand.KEY.SUB}}   a brand.json value (values may hold tokens too, e.g. footer -> {{year}})
  {{year}}                            year of hub/src/data/highlights.json "generated" (deterministic, not the clock)
  {{shell.pinUrl}} {{shell.integrity}} {{shell.csp}}   the pinned shared shell (hub/src/config.json)
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
shell.keep sha256 values in site.json are filled from the rendered files.

Usage: python3 tools/brand_render.py [--check] [--brand PATH] [--out DIR] [--src DIR]
  --check  render to a temp dir and fail (exit 1) if hub/site differs (names every differing file)
"""
import argparse, filecmp, hashlib, json, os, re, sys, tempfile, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
        if not KEY_RE.match(k):
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


class Renderer:
    def __init__(self, src, brand_path, out):
        self.src, self.out = src, out
        self.cfg = json.load(open(os.path.join(src, 'config.json'), encoding='utf-8'))
        brand = json.load(open(brand_path, encoding='utf-8'))
        hl = json.load(open(os.path.join(src, 'data', 'highlights.json'), encoding='utf-8'))
        year = str(hl.get('generated', ''))[:4]
        if not re.match(r'^\d{4}$', year):
            raise RenderError('hub/src/data/highlights.json has no "generated" year')
        sh = self.cfg['shell']
        pin = 'https://cdn.jsdelivr.net/gh/%s@%s/shell/%s/factory.js' % (sh['repo'], sh['sha'], sh['base'])
        csp = "script-src 'self' %s; object-src 'none'; base-uri 'none'; font-src 'self'" % (pin.rsplit('/', 1)[0] + '/')
        if re.search(r'[^\x20-\x7e]|,', csp):
            raise RenderError('CSP must be printable ASCII without commas')
        self.ctx = {'brand': brand, 'year': year,
                    'shell': {'pinUrl': pin, 'integrity': sh['integrity'], 'csp': csp, 'base': sh['base']}}
        prefix = brand.get('topicPathPrefix', '')
        if not re.match(r'^/[a-z0-9][a-z0-9-]*/$', prefix):
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
            if not re.match(r'^[a-z0-9-]+$', name) or not os.path.isfile(p):
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
                if not KEY_RE.match(k[4:]):
                    raise RenderError('%s: bad token {{%s}}' % (where, k))
                return urllib.parse.quote(expand(lookup(ctx, k[4:]), ctx), safe='')
            if not KEY_RE.match(k):
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
        for k in site.get('shell', {}).get('keep', []):
            p = os.path.join(self.out, k['file'])
            if not os.path.isfile(p):
                raise RenderError('site.json shell.keep %s was not rendered' % k['file'])
            k['sha256'] = sha256_file(p)
        rail = os.path.join(self.src, 'data', 'rail.json')
        if os.path.isfile(rail):
            site.setdefault('rail', {})['outbound'] = json.load(open(rail, encoding='utf-8'))
        data = (json.dumps(site, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
        self.write('site.json', data)
        self.assets['/site.json'] = hashlib.sha256(data).hexdigest()[:10]
        missing = [n for n in names if n.endswith('.html') and n not in pages]
        if missing:
            raise RenderError('templates without a "pages" entry in config.json: %s' % ', '.join(missing))
        for n, meta in sorted(pages.items()):
            page = {k: expand(v, self.ctx) if isinstance(v, str) else v for k, v in meta.items()}
            text = self.render_text(open(os.path.join(tdir, n), encoding='utf-8').read(), '.html', page, where=n)
            self.write(self.out_path(n), text.encode('utf-8'))
        return self

    def render_topic(self, topic):
        """Render hub/src/topic-template.html for one topic dict (HUB_COPY 4a-4e). Not emitted to hub/site yet: the
        topic layer ships in its own PR; tests render it with a dummy topic. Call after run() (assets are known)."""
        need = ('slug', 'name', 'description', 'longDescription', 'goodPosts', 'offTopic', 'rulesShort')
        miss = [k for k in need if not str(topic.get(k, '')).strip()]
        if miss:
            raise RenderError('topic is missing %s' % ', '.join(miss))
        if not re.match(r'^[a-z0-9][a-z0-9-]*$', topic['slug']):
            raise RenderError('topic slug %r must be lowercase letters, digits and dashes' % topic['slug'])
        topic = dict({'legacyDomain': ''}, **topic)
        page = {'title': topic['name'] + ', ' + self.ctx['brand']['name'], 'description': topic['description']}
        text = open(os.path.join(self.src, 'topic-template.html'), encoding='utf-8').read()
        return self.render_text(text, '.html', page, where='topic-template.html', extra={'topic': topic})


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
