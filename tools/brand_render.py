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
  {{asset:brand.KEY}}                 same, but the path is a brand.json string (the cat mark and its sizes)
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
import topic_slug, topic_status, logo_mask, og_card  # noqa: E402

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


def og_meta(template, ctx):
    """Open Graph and Twitter tags. A page that already sets a property keeps that tag.
    Pages without og:image still receive the share image."""
    have = set(re.findall(r'<meta\s+(?:property|name)="((?:og|twitter):[^"]+)"', template))
    brand = ctx['brand']
    logo = brand.get('logo') or {}
    page = ctx.get('page') or {}
    domain = brand['primaryDomain']
    path = logo.get('ogImage') or '/og.png'
    image = 'https://%s%s' % (domain, path)
    title = expand(str(page.get('title') or brand['name']), ctx)
    desc = expand(str(page.get('description') or brand['tagline']), ctx)
    url = page.get('canonical') or ('https://%s/' % domain)
    alt = '%s cat logo' % brand['name']
    rows = [
        ('property', 'og:type', 'website'),
        ('property', 'og:site_name', brand['name']),
        ('property', 'og:title', title),
        ('property', 'og:description', desc),
        ('property', 'og:url', url),
        ('property', 'og:image', image),
        ('property', 'og:image:width', str(og_card.WIDTH)),
        ('property', 'og:image:height', str(og_card.HEIGHT)),
        ('property', 'og:image:alt', alt),
        ('name', 'twitter:card', 'summary_large_image'),
        ('name', 'twitter:title', title),
        ('name', 'twitter:description', desc),
        ('name', 'twitter:image', image),
    ]
    lines = []
    for attr, key, value in rows:
        if key in have:
            continue
        lines.append('  <meta %s="%s" content="%s">' % (attr, key, html_attr(str(value))))
    return '\n'.join(lines)


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

# Partner rooms (hub slot). The room name string lives only in rooms/<id>/site.json "displayName".
# partnerRooms[].displayName references that field. The widget stays empty unless enabled is true,
# or the render is a preview that forces the flag on. Never written into hub/site by --preview-partners.
PARTNER_CAP = 2
DISPLAY_REF = re.compile(r'^@rooms/([a-z0-9-]+)/site\.json#displayName$')
PARTNER_CFG_REF = re.compile(r'^@partners/([a-z0-9-]+)/config\.json#displayName$')
LOCAL_PATH = re.compile(r'^/partners/[a-z0-9-]+/$')


def partner_initials(name):
    parts = re.findall(r'[A-Za-z0-9]+', name or '')
    if not parts:
        return '?'
    if len(parts) == 1 or len(parts[0]) <= 2:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def load_partner_config(hub_rooms_path, rooms_root):
    """Resolve hub/src/rooms.json partnerRooms against each room site.json. Does not decide visibility."""
    cfg = json.load(open(hub_rooms_path, encoding='utf-8'))
    raw = cfg.get('partnerRooms') or []
    if not isinstance(raw, list):
        raise RenderError('partnerRooms must be a list')
    organic = {r.get('room') for r in cfg.get('rooms') or [] if isinstance(r, dict)}
    featured = set(cfg.get('featuredRooms') or [])
    order = set(cfg.get('roomOrder') or [])
    out = []
    for p in raw:
        if not isinstance(p, dict):
            raise RenderError('partnerRooms entry must be an object')
        room = p.get('room')
        if not isinstance(room, str) or not re.fullmatch(r'[a-z0-9-]{1,40}', room):
            raise RenderError('partner room id is missing')
        if room in organic or room in featured or room in order:
            raise RenderError('partner room %s must stay out of the organic rooms list, featuredRooms, and roomOrder' % room)
        for key in ('sponsor', 'label', 'disclosure', 'since', 'displayName', 'enabled'):
            if key not in p:
                raise RenderError('partner room %s is missing %s' % (room, key))
        if p['enabled'] is not True and p['enabled'] is not False:
            raise RenderError('partner room %s enabled must be true or false' % room)
        if p['label'] != 'Sponsored':
            raise RenderError('partner room %s label must be Sponsored' % room)
        if p['sponsor'] != '@displayName':
            raise RenderError('partner room %s sponsor must reference @displayName' % room)
        if p['disclosure'] != 'Sponsored by {{displayName}}':
            raise RenderError('partner room %s disclosure must be Sponsored by {{displayName}}' % room)
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(p['since'])):
            raise RenderError('partner room %s since must be YYYY-MM-DD' % room)
        ref = p['displayName']
        path = p.get('path')
        if not isinstance(path, str) or not LOCAL_PATH.fullmatch(path):
            raise RenderError('partner room %s path must be /partners/<slug>/' % room)
        if re.search(r'https?:|usserviceanimals\.org|dogacademy\.org', path, re.I):
            raise RenderError('partner room %s path must stay on this hub' % room)
        m = DISPLAY_REF.fullmatch(ref if isinstance(ref, str) else '')
        cfg_m = PARTNER_CFG_REF.fullmatch(ref if isinstance(ref, str) else '')
        if m and m.group(1) == room:
            site_path = os.path.join(rooms_root, room, 'site.json')
        elif cfg_m and cfg_m.group(1) == room:
            site_path = os.path.join(os.path.dirname(hub_rooms_path), 'partners', room, 'config.json')
        else:
            raise RenderError('partner room %s displayName must reference its single config field' % room)
        if not os.path.isfile(site_path):
            raise RenderError('partner room %s config is missing' % room)
        site = json.load(open(site_path, encoding='utf-8'))
        name = site.get('displayName')
        if not isinstance(name, str) or not name.strip() or name != name.strip() or '\n' in name:
            raise RenderError('partner room %s displayName must be a single non-empty line' % room)
        if re.search(r'[\u2013\u2014]', name):
            raise RenderError('displayName must not use an en or em dash')
        tagline = site.get('tagline') if isinstance(site.get('tagline'), str) else ''
        if re.search(r'[\u2013\u2014]', tagline):
            raise RenderError('partner room %s tagline must not use an en or em dash' % room)
        out.append({
            'room': room,
            'name': name,
            'tagline': tagline,
            'path': path,
            'sponsor': name,
            'label': 'Sponsored',
            'disclosure': 'Sponsored by ' + name,
            'since': p['since'],
            'enabled': p['enabled'] is True,
            'initials': partner_initials(name),
        })
    return out


def shown_partners(entries, preview):
    """Rooms that render. Preview forces the flag on. More than PARTNER_CAP is an error, not a silent drop."""
    shown = [e for e in entries if e['enabled'] is True or preview]
    if len(shown) > PARTNER_CAP:
        raise RenderError('Partner rooms widget is capped at %d' % PARTNER_CAP)
    return shown


def partner_cards_html(shown):
    """One card per room. Sponsored and Sponsored by <name> are in the HTML, not behind a hover."""
    rows = []
    for p in shown:
        tag = ('<span class="partner-room-tagline">%s</span>' % html_attr(p['tagline'])) if p['tagline'] else ''
        rows.append(
            '<a class="partner-room" href="%s">'
            '<span class="post-avatar" style="background:#2f3336" aria-hidden="true">%s</span>'
            '<span class="partner-room-text">'
            '<span class="sponsored-label">Sponsored</span>'
            '<span class="partner-room-name">%s</span>%s'
            '<span class="partner-disclosure">%s</span>'
            '</span></a>' % (html_attr(p['path']), html_attr(p['initials']), html_attr(p['name']), tag, html_attr(p['disclosure'])))
    return ''.join(rows)


def partner_section_html(shown, extra_class, section_id):
    if not shown:
        return ''
    return (
        '<section class="partner-rooms %s" id="%s" aria-label="Partner rooms">'
        '<h2 class="partner-rooms-title">Partner rooms</h2>'
        '<div class="partner-rooms-body">%s</div>'
        '<p class="partner-rooms-why"><a href="/partners.html">Why am I seeing this?</a></p>'
        '</section>' % (extra_class, section_id, partner_cards_html(shown)))


def partner_widget_html(shown):
    """Desktop rail. Empty only when nothing is enabled."""
    return partner_section_html(shown, 'partner-rooms-rail', 'partner-rooms')


def partner_list_html(shown, legal_entity):
    if not shown:
        return '<p>No partner room is listed on the hub right now.</p>'
    items = ''.join(
        '<li><strong>%s</strong>. <span class="partner-disclosure">%s</span> Operated by %s.</li>'
        % (html_attr(p['name']), html_attr(p['disclosure']), html_attr(legal_entity)) for p in shown)
    return '<h2>Listed on the hub</h2><ul>%s</ul>' % items


class Renderer:
    def __init__(self, src, brand_path, out, preview_partners=False, rooms_root=None):
        self.src, self.out = src, out
        self.preview_partners = bool(preview_partners)
        self.rooms_root = rooms_root or os.path.join(ROOT, 'rooms')
        self.partner_entries = []
        self.partner_shown = []
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
        # footer: "Topics (soon)" until at least one rendered topic is active or quiet (topic_status: only those are live
        # pages); today approved_waves.json is empty, so every topic is hidden and the label keeps "(soon)"
        live = [t for t in self.topics() if t.get('status') in ('active', 'quiet')]
        self.ctx['topicsNav'] = {'soon': '' if live else ' (soon)'}
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
                if path.startswith('brand.'):
                    if not KEY_RE.fullmatch(path):
                        raise RenderError('%s: bad token {{%s}}' % (where, k))
                    path = expand(lookup(ctx, path), ctx)
                if path not in self.assets:
                    raise RenderError('%s: {{%s}} names no rendered asset' % (where, k))
                return path + '?v=' + self.assets[path]
            if k == 'footer:links':
                return footer_links(ctx)
            if k == 'og:meta':
                return og_meta(text, ctx)
            if k == 'partner:widget':
                return partner_widget_html(self.partner_shown)
            if k == 'partner:feed':
                return partner_section_html(self.partner_shown, 'partner-rooms-feed', 'partner-rooms-feed')
            if k == 'partner:roomsTab':
                return partner_section_html(self.partner_shown, 'partner-rooms-directory', 'partner-rooms-directory')
            if k == 'partner:list':
                return partner_list_html(self.partner_shown, self.ctx['brand']['legalEntity'])
            if k == 'partner:ogTitle':
                return html_attr(expand(lookup(ctx, 'page.title'), ctx))
            if k == 'partner:ogDescription':
                return html_attr(expand(lookup(ctx, 'page.description'), ctx))
            if k == 'partnerRoom:body':
                return self.partner_room_body
            if k == 'partnerRoom:ogTitle':
                return html_attr(self.partner_room_title)
            if k == 'partnerRoom:ogDescription':
                return html_attr(self.partner_room_description)
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

    def fork_shell_file(self, name, require_config_integrity=False):
        """Hub-only header fork of one file from shell/<base>/. The pinned file is verified first
        against SHELL.json (and, for factory.js, against config.json shell.integrity). Then exactly
        one line changes: the header comment line naming the source repo becomes FORK_HEADER.
        Every other byte is identical. Returns (fork bytes, fork sha256, fork SRI sha384)."""
        sh = self.cfg['shell']
        man = json.load(open(os.path.join(ROOT, 'shell', sh['base'], 'SHELL.json'), encoding='utf-8'))['files'][name]
        data = open(os.path.join(ROOT, 'shell', sh['base'], name), 'rb').read()
        sri = 'sha384-' + base64.b64encode(hashlib.sha384(data).digest()).decode()
        if require_config_integrity and not (sri == sh['integrity'] == man['integrity']):
            raise RenderError('shell/%s/%s sha384 %s != config.json shell.integrity / SHELL.json' % (sh['base'], name, sri))
        if (not require_config_integrity) and sri != man['integrity']:
            raise RenderError('shell/%s/%s sha384 %s != SHELL.json' % (sh['base'], name, sri))
        if hashlib.sha256(data).hexdigest() != man['sha256'] or len(data) != man['bytes']:
            raise RenderError('shell/%s/%s sha256/bytes != SHELL.json' % (sh['base'], name))
        lines = data.split(b'\n')
        hits = [i for i, ln in enumerate(lines) if FORK_HEADER_FROM in ln]
        if len(hits) != 1 or not lines[hits[0]].lstrip().startswith(b'*'):
            raise RenderError('shell/%s/%s: expected exactly one header comment line with %r (found %d)'
                              % (sh['base'], name, FORK_HEADER_FROM.decode(), len(hits)))
        lines[hits[0]] = (FORK_HEADER % sh['base']).encode()
        fork = b'\n'.join(lines)
        fsri = 'sha384-' + base64.b64encode(hashlib.sha384(fork).digest()).decode()
        return fork, hashlib.sha256(fork).hexdigest(), fsri

    def shell_bytes(self):
        """The self-hosted hub fork of shell/<base>/factory.js (never re-branded). See fork_shell_file."""
        return self.fork_shell_file('factory.js', require_config_integrity=True)

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

    def prepare_partners(self):
        path = os.path.join(self.src, 'rooms.json')
        entries = load_partner_config(path, self.rooms_root) if os.path.isfile(path) else []
        self.partner_entries = entries
        self.partner_shown = shown_partners(entries, self.preview_partners)

    def emit_logo(self):
        """Copy brand.logo files into the site. Bytes are unchanged. Sizes are the files
        named in brand.json, not a resample, so a new drawing is a file drop.
        Dark-tab favicon PNGs and the SVG icon are painted from those alphas."""
        try:
            pairs = logo_mask.plan(self.ctx['brand'])
        except logo_mask.LogoError as e:
            raise RenderError(str(e))
        mask_bytes = None
        sized = {}
        root = os.path.realpath(ROOT)
        for rel, href, px in pairs:
            full = os.path.realpath(os.path.join(ROOT, rel))
            if not full.startswith(root + os.sep) or not os.path.isfile(full):
                raise RenderError('brand.logo file is missing: %s' % rel)
            data = open(full, 'rb').read()
            try:
                w, h = logo_mask.png_wh(data)
            except logo_mask.LogoError as e:
                raise RenderError('%s: %s' % (rel, e))
            if px is not None and (w, h) != (px, px):
                raise RenderError('%s is %dx%d, brand.logo expects %d' % (rel, w, h, px))
            if w < 1 or h < 1 or w > 4096 or h > 4096:
                raise RenderError('%s has an unexpected size' % rel)
            self.write(href.lstrip('/'), data)
            self.assets[href] = hashlib.sha256(data).hexdigest()[:10]
            if px is None:
                mask_bytes = data
            else:
                sized[px] = (href, data)
        try:
            card = og_card.build(self.ctx['brand'], mask_bytes)
        except og_card.CardError as e:
            raise RenderError(str(e))
        og_href = self.ctx['brand']['logo'].get('ogImage') or '/og.png'
        if not og_href.startswith('/') or '..' in og_href:
            raise RenderError('brand.logo.ogImage must be a site path')
        self.write(og_href.lstrip('/'), card)
        self.assets[og_href] = hashlib.sha256(card).hexdigest()[:10]
        self.emit_favicon_theme(sized)

    def emit_favicon_theme(self, sized):
        """Paint one dark-tab PNG per favicon size from the copied alpha and logo.colorDark.
        Write cat-favicon.svg with the 48px pair embedded. Apple touch stays the copied 256."""
        logo = self.ctx['brand']['logo']
        color = str(logo['colorDark'])
        embed = None
        for px in logo_mask.FAVICON_PX:
            if px not in sized:
                raise RenderError('favicon size %d is missing from brand.logo' % px)
            href, data = sized[px]
            try:
                twin = logo_mask.dark_href(href)
                dark = logo_mask.paint(data, color)
            except logo_mask.LogoError as e:
                raise RenderError(str(e))
            self.write(twin.lstrip('/'), dark)
            self.assets[twin] = hashlib.sha256(dark).hexdigest()[:10]
            logo['icon%dDark' % px] = twin
            if px == logo_mask.SVG_EMBED_PX:
                embed = (data, dark)
        if embed is None:
            raise RenderError('favicon svg embed size is not a favicon size')
        try:
            svg = logo_mask.favicon_svg(embed[0], embed[1], logo_mask.SVG_EMBED_PX)
        except logo_mask.LogoError as e:
            raise RenderError(str(e))
        href = logo_mask.FAVICON_SVG
        raw = svg.encode('utf-8')
        self.write(href.lstrip('/'), raw)
        self.assets[href] = hashlib.sha256(raw).hexdigest()[:10]
        logo['favicon'] = href

    def run(self):
        os.makedirs(self.out, exist_ok=True)
        self.prepare_partners()
        self.emit_logo()
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
        # v1.2.9 lazy companion: same header-only fork, so a Google tap can load factory-signin.js
        # from the same directory as factory.js.
        signin_name = 'factory-signin.js'
        signin_src = os.path.join(ROOT, 'shell', self.cfg['shell']['base'], signin_name)
        if os.path.isfile(signin_src):
            sdata, _, _ = self.fork_shell_file(signin_name)
            self.write('shell/%s/%s' % (self.cfg['shell']['base'], signin_name), sdata)
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
        # Partner rooms render to /partners/<slug>/ even when hubSlot is false. A true hubSlot is refused:
        # nothing in this renderer may add one to featuredRooms, roomOrder, or hub navigation.
        self._partner_rooms = self.partner_rooms()
        ns = site.setdefault('shell', {}).setdefault('noShell', [])
        ns += [self.topic_path(t['slug']) for t in topics]
        ns += [self.partner_rel(slug) for slug, _room, _html in self._partner_rooms]
        import partner_room_render as PR
        try:
            for rel in PR.room_page_rels():
                if rel not in ns:
                    ns.append(rel)
        except PR.RoomError as e:
            raise RenderError(str(e))
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
            if n == 'partners.html' and self.partner_shown:
                names = ', '.join(p['name'] for p in self.partner_shown)
                page['title'] = '%s, %s' % (names, page['title'])
                page['description'] = '%s. %s' % (self.partner_shown[0]['disclosure'], page['description'])
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
        for slug, room, html_path in self._partner_rooms:
            self.write(self.partner_rel(slug), self.render_partner(slug, room, html_path).encode('utf-8'))
        self.write('sitemap.xml', self.sitemap(topics).encode('utf-8'))
        self.write_partner_room()
        return self

    def write_partner_room(self):
        """Static room home a hosting preview can serve. noindex. The hub widget flag does not hide this page."""
        import partner_room_render as PR
        site_path = os.path.join(self.rooms_root, 'dogacademy-partner', 'site.json')
        if not os.path.isfile(site_path):
            raise RenderError('partner room site.json is missing')
        brand_name = self.ctx['brand']['name']
        whomark = PR.load(PR.WHOMARK)
        fr = PR.fragments(PR.load(site_path), self.ctx['brand'], whomark)
        tpl = open(os.path.join(self.src, 'partner-room', 'home.html'), encoding='utf-8').read()

        def emit(rel, title, description, body):
            self.partner_room_body = body
            self.partner_room_title = title
            self.partner_room_description = description
            page = {'title': title, 'description': description, 'robots': topic_status.NOINDEX,
                    'canonical': self.canonical(rel)}
            text = self.render_text(tpl, '.html', page, where=rel)
            self.write(rel, text.encode('utf-8'))

        emit('partners/dogacademy/index.html', '%s, %s' % (fr['name'], brand_name),
             '%s %s' % (fr['tagline'], fr['disclosure']), PR.body_html(fr))
        for a in fr['article_pack']['articles']:
            emit(PR.article_rel(a['slug']), '%s, %s' % (a['title'], brand_name), a['dek'], PR.article_html(fr, a))

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


    def partner_rel(self, slug):
        return 'partners/%s/index.html' % slug

    def partner_rooms(self):
        """hub/src/partners/<slug>/{config.json,index.html}. displayName is the only name field.

        hubSlot must be false. These pages are static and noindex. They are not added to the sitemap
        or to any hub nav list."""
        root = os.path.join(self.src, 'partners')
        if not os.path.isdir(root):
            return []
        found = []
        for slug in sorted(os.listdir(root)):
            d = os.path.join(root, slug)
            if slug.startswith('.') or not os.path.isdir(d):
                continue
            if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,48}', slug):
                raise RenderError('partner room directory %r must be a lowercase slug' % slug)
            cfg_path = os.path.join(d, 'config.json')
            html_path = os.path.join(d, 'index.html')
            if not (os.path.isfile(cfg_path) and os.path.isfile(html_path)):
                raise RenderError('partner room %s needs config.json and index.html' % slug)
            cfg = json.load(open(cfg_path, encoding='utf-8'))
            if not isinstance(cfg, dict):
                raise RenderError('partner room %s config must be an object' % slug)
            if cfg.get('slug') != slug:
                raise RenderError('partner room %s: config slug must match the directory' % slug)
            name = cfg.get('displayName')
            if not isinstance(name, str) or not name.strip() or name != name.strip():
                raise RenderError('partner room %s: displayName must be a non-empty string' % slug)
            if any(x in name for x in ('{{', '}}', '<', '>')):
                raise RenderError('partner room %s: displayName must be plain text' % slug)
            if cfg.get('hubSlot') is not False:
                raise RenderError('partner room %s: hubSlot must be false so it stays out of hub navigation' % slug)
            room = {}
            for k, v in cfg.items():
                if k.startswith('_') or isinstance(v, bool):
                    continue
                if not isinstance(v, str):
                    raise RenderError('partner room %s: %s must be a string' % (slug, k))
                if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', k):
                    raise RenderError('partner room %s: bad key %r' % (slug, k))
                room[k] = v
            found.append((slug, room, html_path))
        return found

    def render_partner(self, slug, room, html_path):
        rel = self.partner_rel(slug)
        extra_desc = room.get('description') or ''
        page = {
            'title': '%s \u00b7 %s' % (room['displayName'], self.ctx['brand']['name']),
            'description': ('Sponsored room. %s. %s' % (room['displayName'], extra_desc)).strip(),
            'robots': topic_status.NOINDEX,
            'canonical': self.canonical(rel),
        }
        text = open(html_path, encoding='utf-8').read()
        if '<!--' in text:
            raise RenderError('%s: partner room HTML cannot contain comments' % rel)
        return self.render_text(text, '.html', page, where=rel, extra={'room': room})


def files_under(d):
    out = set()
    for base, _, fs in os.walk(d):
        for f in fs:
            out.add(os.path.relpath(os.path.join(base, f), d).replace(os.sep, '/'))
    return out


def render(src=None, brand=None, out=None, preview_partners=False, rooms_root=None):
    src = src or os.path.join(ROOT, 'hub', 'src')
    brand = brand or os.path.join(ROOT, 'brand', 'brand.json')
    out = out or os.path.join(ROOT, 'hub', 'site')
    return Renderer(src, brand, out, preview_partners=preview_partners, rooms_root=rooms_root).run()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--preview-partners', action='store_true',
                    help='force partner rooms on, for a local preview only; refuses to write hub/site')
    ap.add_argument('--brand')
    ap.add_argument('--src')
    ap.add_argument('--out')
    a = ap.parse_args(argv)
    target = a.out or os.path.join(ROOT, 'hub', 'site')
    live = os.path.realpath(os.path.join(ROOT, 'hub', 'site'))
    try:
        if a.preview_partners and (a.check or os.path.realpath(target) == live):
            print('brand_render: --preview-partners writes a separate --out directory, never hub/site, and not with --check',
                  file=sys.stderr)
            return 2
        if a.check:
            with tempfile.TemporaryDirectory() as tmp:
                render(a.src, a.brand, tmp, preview_partners=False)
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
        r = render(a.src, a.brand, target, preview_partners=a.preview_partners)
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
