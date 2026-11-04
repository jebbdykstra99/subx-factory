#!/usr/bin/env python3
"""Hub (hub/src -> hub/site) and brand/brand.json: render is reproducible, a dummy rename reaches every page with no
brand literal left, every page carries the preview locks + strict CSP + footer, and tools/shell_drift.py scores the
hub OK with the CSP rule enforced. Offline; temp dirs only (the hub data files are not refetched)."""
import json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import brand_render as BR  # noqa: E402

SITE = os.path.join(ROOT, 'hub', 'site')
SRC = os.path.join(ROOT, 'hub', 'src')
BRAND = os.path.join(ROOT, 'brand', 'brand.json')
fails = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def read(p):
    return open(p, encoding='utf-8').read()


def files(d):
    return sorted(BR.files_under(d))


TEXT = BR.TEXT_EXT
cfg = json.load(open(os.path.join(SRC, 'config.json')))
brand = json.load(open(BRAND))
PIN = 'https://cdn.jsdelivr.net/gh/%s@%s/shell/%s/factory.js' % (cfg['shell']['repo'], cfg['shell']['sha'], cfg['shell']['base'])
PIN_DIR = PIN.rsplit('/', 1)[0] + '/'
CSP = "script-src 'self' %s; object-src 'none'; base-uri 'none'" % PIN_DIR

# ---- brand.json ----
want_keys = ['name', 'legalEntity', 'primaryDomain', 'shortName', 'tagline', 'takedownEmail', 'topicPathPrefix',
             'reviewerLine', 'taglineOptions', 'contactPhone', 'mailingAddress', 'roomNoun', 'topicNoun',
             'disclosureMark', 'nonAffiliation', 'notAdvice', 'footer']
ok(list(brand) == want_keys, 'brand.json has the 17 keys of the brand.json draft, in order, and no _draft (%s)' % list(brand))
ok(brand['tagline'] == 'Small rooms for big interests.' and brand['tagline'] in brand['taglineOptions'], 'brand.json tagline is the chosen option')
ok(brand['legalEntity'] == 'SubX, LLC' and brand['takedownEmail'] == 'takedown@subx.it', 'brand.json legal entity + takedown email')
ok(re.fullmatch(r'[0-9a-f]{40}', cfg['shell']['sha']) is not None, 'hub pin is a full 40-char SHA')
ok(os.path.isfile(os.path.join(ROOT, 'shell', cfg['shell']['base'], 'factory.js')), 'hub pin base folder exists in shell/')

# ---- render is reproducible and hub/site is current ----
r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'brand_render.py'), '--check'], capture_output=True, text=True)
ok(r.returncode == 0, 'brand_render --check: hub/site is current (%s%s)' % (r.stdout.strip(), r.stderr.strip()))
with tempfile.TemporaryDirectory() as t:
    BR.render(out=os.path.join(t, 'a')); BR.render(out=os.path.join(t, 'b'))
    same = all(open(os.path.join(t, 'a', f), 'rb').read() == open(os.path.join(t, 'b', f), 'rb').read() for f in files(os.path.join(t, 'a')))
    ok(same and files(os.path.join(t, 'a')) == files(os.path.join(t, 'b')), 'two renders are byte-identical (no clock, no randomness)')
    # stale detection: --check names a hand-edited file
    shutil.copytree(os.path.join(t, 'a'), os.path.join(t, 'c'))
    open(os.path.join(t, 'c', 'about.html'), 'a').write('<!-- edit -->')
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'brand_render.py'), '--check', '--out', os.path.join(t, 'c')], capture_output=True, text=True)
    ok(r.returncode == 1 and 'about.html' in r.stdout, '--check fails and names a hand-edited output file (%s)' % r.stdout.strip())

# vendored shared files are byte copies with today's brand
for v in cfg['vendor']:
    ok(open(os.path.join(ROOT, v['from']), 'rb').read() == open(os.path.join(SITE, v['to']), 'rb').read(), 'vendored %s == %s (byte copy)' % (v['to'], v['from']))

# ---- pages ----
pages = [f for f in files(SITE) if f.endswith('.html')]
topic_index = brand['topicPathPrefix'].strip('/') + '/index.html'
ok(sorted(pages) == sorted(['index.html', 'rooms.html', 'about.html', topic_index, 'terms.html', 'privacy.html', 'guidelines.html', 'report.html', '404.html']),
   'hub pages: home, rooms, about, topic index stub, 4 legal, 404 (%s)' % pages)
site = json.load(open(os.path.join(SITE, 'site.json')))
sh = site['shell']
no_shell = set(x.lstrip('/') for x in sh.get('noShell', []))
ok(site['siteId'] == 'subx' and site['accountsOpen'] is False and sh['cspRequired'] is True and sh['base'] == cfg['shell']['base'] and not sh.get('fork'),
   'site.json: siteId subx, accounts closed, cspRequired true, base = pin base, no fork')
leg = json.load(open(os.path.join(ROOT, 'tools', 'csp_legacy_rooms.json')))['rooms']
ok('subx' not in leg and 'hub' not in leg, 'the hub is not on the CSP legacy list')
ok(not sh.get('recaptcha') and 'recaptcha' not in ''.join(read(os.path.join(SITE, p)) for p in pages).lower(), 'no reCAPTCHA (shell.recaptcha not set)')
ok('index.html' not in no_shell and no_shell == set(pages) - {'index.html'}, 'index.html runs the shell; every other page is a declared noShell static page')

HEAD_RE = re.compile(r'^<!DOCTYPE html>\s*<html lang="en">\s*<head>\s*<meta charset="UTF-8">\s*<meta http-equiv="Content-Security-Policy" content="([^"]*)">', re.I)
for p in pages:
    h = read(os.path.join(SITE, p))
    m = HEAD_RE.match(h)
    ok(m is not None and m.group(1) == CSP, '%s: meta CSP is the first element after charset, http-equiv exact, strict policy' % p)
    if m:
        c = m.group(1)
        ok(all(32 <= ord(ch) < 127 for ch in c) and ',' not in c and PIN_DIR in c.split(';')[0].split(), '%s: CSP is ASCII, no commas, script-src lists the pin folder' % p)
    ok(h.count('Content-Security-Policy') == 1, '%s: exactly one CSP meta' % p)
    ok('<meta name="robots" content="noindex,nofollow">' in h, '%s: robots noindex,nofollow' % p)
    ok('<div class="preview-banner" role="status">Preview only. Not public and not indexed.</div>' in h, '%s: preview banner' % p)
    fm = re.search(r'<footer class="legal-footer"[^>]*>(.*?)</footer>', h, re.S)
    ok(fm is not None and brand['legalEntity'] in fm.group(1) and brand['takedownEmail'] in fm.group(1) and brand['nonAffiliation'] in fm.group(1),
       '%s: legal footer with %s, the takedown email and the non-affiliation line' % (p, brand['legalEntity']))
    pins = re.findall(r'<script\b[^>]*\bsrc="([^"]*factory[^"]*)"[^>]*>', h)
    if p == 'index.html':
        tag = re.search(r'<script src="%s" integrity="%s" crossorigin="anonymous" data-site="/site\.json\?v=[0-9a-f]{10}"></script>' % (re.escape(PIN), re.escape(cfg['shell']['integrity'])), h)
        ok(tag is not None and pins == [PIN], 'index.html: the pinned shell (full SHA, SRI, crossorigin, data-site) and no other factory script')
    else:
        ok(pins == [], '%s: static page loads no factory script (declared noShell)' % p)
    scripts = re.findall(r'<script\b([^>]*)>(.*?)</script>', h, re.S)
    ok(all(re.search(r'\bsrc="', a) and not body.strip() for a, body in scripts), '%s: no inline <script>' % p)
    ok(re.search(r'\son[a-z]+\s*=', h, re.I) is None and 'javascript:' not in h.lower(), '%s: no on*= handlers or javascript: URLs' % p)
    ok(re.search(r'<(iframe|frame|object|embed)\b|srcdoc|http-equiv="refresh"', h, re.I) is None, '%s: no frames, embeds or meta refresh' % p)
    ok('[gate' not in h.lower() and 'ship-when-live' not in h.lower() and 'ship when live' not in h.lower(), '%s: no gated copy markers' % p)
    ok(re.search(r'\{\{|\}\}', h) is None, '%s: no leftover tokens' % p)
    for href in re.findall(r'href="(/[^"]*)"', h):
        path = href.split('?')[0].split('#')[0]
        tgt = path.lstrip('/') or 'index.html'
        if tgt.endswith('/'):
            tgt += 'index.html'
        if not os.path.exists(os.path.join(SITE, tgt)):
            ok(False, '%s: internal link %s resolves' % (p, href))
    ok(True, '%s: internal links resolve' % p)

idx = read(os.path.join(SITE, 'index.html'))
ok('<h1 class="hub-title">Small rooms for big interests.</h1>' in idx or '>Small rooms for big interests.</h1>' in idx, 'home: tagline headline')
ok('id="hub-feed"' in idx and 'id="hub-rooms"' in idx, 'home: highlights feed + rooms tab containers')
ok('href="%s"' % brand['topicPathPrefix'] in idx, 'home: links the topic index stub')
ok('id="hub-rooms"' in read(os.path.join(SITE, 'rooms.html')) and '/hub.js?v=' in read(os.path.join(SITE, 'rooms.html')), 'rooms.html: directory container + hub.js')
hl = json.load(open(os.path.join(SITE, 'highlights.json')))
rooms = json.load(open(os.path.join(SITE, 'rooms.json')))
ok(len(hl['items']) > 0 and all(re.fullmatch(r'https://[a-z0-9.-]+\.[a-z]{2,}/\?p=[A-Za-z0-9_-]+', it['url']) for it in hl['items']), 'highlights.json: items, each linking to its room post')
# Key 1 edit E1: highlights skip dash and "Seed" posts (build_highlights.text_rule / check); quoted text never edited
sys.path.insert(0, os.path.join(ROOT, 'hub', 'src'))
import build_highlights as BH  # noqa: E402
for t, want in (('Race day \u2014 who is in?', 'dash'), ('Laps 10\u201312 were wild', 'dash'), ('Seed: first post', 'seed_prefix'),
                ('  seed post here', 'seed_prefix'), ('SEEDED thread', 'seed_prefix'), ('A seed of an idea', None),
                ('Plain text - with a hyphen', None)):
    ok(BH.text_rule(t) == want, 'build_highlights.text_rule(%r) == %r' % (t, want))
doc = {'name': 'projects/x/databases/(default)/documents/posts/P1', 'createTime': '2026-11-01T00:00:00Z'}
base = {'siteId': 'x', 'authorUid': 'u1', 'createdAt': '2026-11-01T00:00:00Z'}
ok(BH.check(dict(base, text='Seed \u2014 hello'), doc, set()) in ('dash', 'seed_prefix')
   and BH.check(dict(base, text='Seedlings up'), doc, set()) == 'seed_prefix'
   and BH.check(dict(base, text='Hello there, all good'), doc, set()) is None, 'build_highlights.check drops dash/Seed posts, keeps plain ones')
src_hl = json.load(open(os.path.join(ROOT, 'hub', 'src', 'data', 'highlights.json'), encoding='utf-8'))
ok(not [it['postId'] for it in src_hl['items'] if BH.text_rule(it['text'])], 'highlights.json: no item with an em/en dash or a "Seed" start')
ok('AT1RMUrXqDWrXqKmGn36' not in json.dumps(hl) and 'AT1RMUrXqDWrXqKmGn36' not in idx, 'highlights: 808chat post AT1RMUrXqDWrXqKmGn36 is gone')
ok(src_hl['counts'] == {r: sum(1 for it in src_hl['items'] if it['room'] == r) for r in src_hl['counts']}
   and sum(src_hl['counts'].values()) == len(src_hl['items']), 'highlights.json: counts match items')
# Key 1 edit E2: sign-up consent wording
ok('(preview stubs, not final counsel)' not in idx and idx.count('Privacy Policy</a> (preview drafts).') == 2,
   'index.html: both sign-up consent lines say "(preview drafts)"')
ok(len(rooms['rooms']) > 0 and [x['url'] for x in site['rail']['outbound']] == ['https://%s/' % x['domain'] for x in rooms['rooms']], 'site.json rail.outbound mirrors rooms.json')

# WHOMARK legend: both AI rows (AI steward + AI-made) on about + topic index
for p in ('about.html', topic_index):
    h = read(os.path.join(SITE, p))
    rows = re.findall(r'<tr>\s*<th scope="row">(.*?)</th>', h, re.S)
    labels = [re.sub(r'<[^>]+>', '', x).strip() for x in rows]
    ok(labels == ['Human-made', 'AI steward', 'AI-made', 'Human + AI'], '%s: WHOMARK legend rows (%s)' % (p, labels))
tiers = set(json.load(open(os.path.join(SITE, 'assets', 'whomark', 'config.json')))['tiers'])
used = set(re.findall(r'data-whomark="([a-z]+)"', read(os.path.join(SITE, 'about.html'))))
ok(used <= tiers, 'legend uses only real whomark tiers (%s of %s)' % (sorted(used), sorted(tiers)))

# topics held for the topic-layer PR
ok(files(os.path.join(SITE, brand['topicPathPrefix'].strip('/'))) == ['index.html'], 'no topic pages seeded (topic folder holds only the index stub)')
ok(not any('topics_wave1' in f for f in BR.files_under(ROOT) if not f.startswith(('.git/', 'node_modules/'))), 'topics_wave1.csv is not in this PR')

# ---- hard rules: private strings never appear; phone + mailing address only on About ----
def scan_files():
    for base in (SITE, SRC, os.path.dirname(BRAND)):
        for f in BR.files_under(base):
            if f.endswith(TEXT) or f.endswith(('.py', '.md', '.csv')):
                yield os.path.join(base, f)
    for f in ('tools/brand_render.py', 'test/hub_brand.test.py', 'hub/firebase.json', 'hub/README.md'):
        if os.path.isfile(os.path.join(ROOT, f)):
            yield os.path.join(ROOT, f)
FORBID = [re.compile(x, re.I) for x in (r'\bjebb(?!dykstra99/subx-factory\b)', r'\bj@sub' + r'x\.it', r'\(?\b310\)?[\s.-]?\d{3}[\s.-]?\d{4}\b',
                                         r'\bden' + r'ver\b', r'peek' + r'ai', r'voka' + r'dots', r'dmca-' + r'1084331')]
hits = []
for p in scan_files():
    if os.path.abspath(p) == os.path.abspath(__file__):
        continue
    t = read(p) if not p.endswith('.png') else ''
    for rx in FORBID:
        for m in rx.finditer(t):
            hits.append('%s: %s' % (os.path.relpath(p, ROOT), m.group(0)))
ok(not hits, 'no private names, emails, 310 numbers, registered-agent city or internal codes in the hub, brand or renderer (%s)' % hits[:5])
for f in files(SITE):
    if not f.endswith(TEXT):
        continue
    t = read(os.path.join(SITE, f))
    if f == 'about.html':
        ok(brand['contactPhone'] in t and brand['mailingAddress'] in t, 'about.html shows the phone and the mailing address')
    else:
        ok(brand['contactPhone'] not in t and '539-5005' not in t and 'Ocean Park' not in t and 'CA 90405' not in t, '%s: no phone or mailing address (About only)' % f)
    emails = set(re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', t)) - {brand['takedownEmail'], 'you@email.com'}
    ok(not emails, '%s: the only email is %s (plus the sign-in field placeholder) (%s)' % (f, brand['takedownEmail'], sorted(emails)))

# ---- shell_drift: OK with the CSP rule enforced (empty legacy list), with and without the hosting config ----
def drift(d, legacy=()):
    out = d.rstrip('/') + '.json'; lf = d.rstrip('/') + '.legacy.json'
    json.dump({'rooms': list(legacy)}, open(lf, 'w'))
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'shell_drift.py'), d, '--json', out, '--csp-legacy', lf], capture_output=True, text=True)
    j = json.load(open(out))
    return j[0] if isinstance(j, list) else (j.get('rooms') or [j])[0]

with tempfile.TemporaryDirectory() as t:
    d = os.path.join(t, 'site'); shutil.copytree(SITE, d)
    r = drift(d)
    ok(r['status'] == 'OK' and not r['findings'] and not r['warnings'], 'shell_drift hub/site = OK, no findings or warnings, CSP enforced (%s %s)' % (r['findings'][:3], r['warnings'][:3]))
    fb = json.load(open(os.path.join(ROOT, 'hub', 'firebase.json')))
    shutil.copy(os.path.join(ROOT, 'hub', 'firebase.json'), os.path.join(d, 'firebase.json'))
    r = drift(d)
    ok(r['status'] == 'OK' and not r['findings'] and not r['warnings'], 'shell_drift hub/site + hub/firebase.json headers = OK (%s %s)' % (r['findings'][:3], r['warnings'][:3]))
    hs = fb['hosting']
    hdr = {h['key']: h['value'] for e in hs['headers'] for h in e['headers']}
    ok(hs['public'] == 'site' and not hs.get('redirects') and not hs.get('rewrites'), 'hub/firebase.json: public site, no redirects or rewrites')
    ok(hdr.get('X-Robots-Tag') == 'noindex, nofollow' and hdr.get('Content-Security-Policy') == CSP + "; frame-ancestors 'none'", 'hub/firebase.json: X-Robots-Tag noindex + header CSP = meta CSP + frame-ancestors')
    # a local shell copy is drift: the hub never vendors factory.js
    shutil.copy(os.path.join(ROOT, 'factory', 'factory.js'), os.path.join(d, 'factory.js'))
    r = drift(d)
    ok(r['status'] == 'DRIFT', 'a local factory.js copy in the hub = DRIFT')
    os.remove(os.path.join(d, 'factory.js'))
    os.remove(os.path.join(d, 'firebase.json'))  # (a strict header CSP would still cover a weak meta; test the meta alone)
    h = read(os.path.join(d, 'about.html')).replace(PIN_DIR + ';', 'https:;', 1)
    open(os.path.join(d, 'about.html'), 'w').write(h)
    r = drift(d)
    ok(r['status'] == 'DRIFT' and any('about.html' in x for x in r['findings']), 'a weakened meta CSP on one hub page = DRIFT')
ok(not any(f.endswith('factory.js') for f in files(SITE)), 'hub/site has no local factory.js')

# ---- dummy rename flows through every hub page ----
dummy = json.loads(json.dumps(brand))
dummy.update({'name': 'Quillnest', 'legalEntity': 'Quillnest Labs, Inc.', 'primaryDomain': 'quillnest.example', 'shortName': 'Quill',
              'tagline': 'Tiny tables for loud ideas.', 'takedownEmail': 'notices@quillnest.example', 'topicPathPrefix': '/z/',
              'reviewerLine': 'a human reviewer at Quillnest Labs, Inc.', 'taglineOptions': ['Tiny tables for loud ideas.'],
              'contactPhone': '+1-555-010-0199', 'mailingAddress': '1 Example Way, Testville, ZZ 00000',
              'roomNoun': {'one': 'table', 'many': 'tables', 'article': 'a', 'One': 'Table', 'Many': 'Tables'},
              'topicNoun': {'one': 'theme', 'many': 'themes', 'One': 'Theme', 'Many': 'Themes'},
              'disclosureMark': 'MAKERMARK', 'nonAffiliation': 'Not affiliated with anyone else.', 'notAdvice': 'Opinions only.',
              'footer': '(c) {{year}} {{brand.legalEntity}} · Terms · Privacy · Report: {{brand.takedownEmail}}'})
# internal ids that are not brand copy: the pin's repo path, the siteId / project ids, a storage key
ALLOW = ['jebbdykstra99/subx-factory', 'subx-factory', '"siteId": "subx"', 'subx-skins', 'subx.vid']
with tempfile.TemporaryDirectory() as t:
    bp = os.path.join(t, 'brand.json'); json.dump(dummy, open(bp, 'w'))
    out = os.path.join(t, 'site')
    BR.Renderer(SRC, bp, out).run()
    names = files(out)
    ok('z/index.html' in names and 't/index.html' not in names, 'rename: topic index follows topicPathPrefix (/z/)')
    left = []
    for f in names:
        if not f.endswith(TEXT):
            continue
        t_ = read(os.path.join(out, f))
        for a in ALLOW:
            t_ = t_.replace(a, '')
        for m in re.finditer(r'sub\s?x|whomark™|small rooms for big|\broom\b|\brooms\b|\btopics?\b', t_, re.I):
            if m.group(0).lower().startswith('sub') or 'small rooms' in m.group(0).lower() or m.group(0) == 'WHOMARK™':
                left.append('%s: %r' % (f, t_[max(0, m.start() - 30):m.end() + 20]))
    ok(not left, 'rename: zero "SubX" / "subx.it" / old tagline literals left in any rendered file outside brand.json (%d: %s)' % (len(left), left[:4]))
    for f in [x for x in names if x.endswith('.html')]:
        h = read(os.path.join(out, f))
        fm = re.search(r'<footer class="legal-footer"[^>]*>(.*?)</footer>', h, re.S)
        ok(fm is not None and 'Quillnest Labs, Inc.' in fm.group(1) and 'notices@quillnest.example' in fm.group(1), 'rename: %s footer carries the new legal entity + email' % f)
        ok('Quillnest' in re.search(r'<title>(.*?)</title>', h).group(1), 'rename: %s title carries the new name' % f)
    about = read(os.path.join(out, 'about.html'))
    ok('+1-555-010-0199' in about and '1 Example Way' in about and 'MAKERMARK' in about and 'Tables' in about, 'rename: About shows the new phone, address, mark and room noun')
    idx_ = read(os.path.join(out, 'index.html'))
    ok('Tiny tables for loud ideas.' in idx_ and 'href="/z/"' in idx_ and 'Browse tables' in idx_, 'rename: home tagline, topic link and CTA noun follow brand.json')
    s_ = json.load(open(os.path.join(out, 'site.json')))
    ok(s_['name'] == 'Quillnest' and s_['domain'] == 'quillnest.example' and 'z/index.html' in s_['shell']['noShell'][2], 'rename: site.json name, domain and noShell path follow brand.json')
    cfgj = read(os.path.join(out, 'assets', 'whomark', 'config.json'))
    ok('AI steward · Quill' in cfgj and 'Operated by Quill' in cfgj, 'rename: vendored whomark config is re-branded (steward label)')
    ok('Operated by Quillnest Labs, Inc. using AI tools' in read(os.path.join(out, 'hub.js')) and
       '.post-steward-pill[title^="Operated by Quill"]' in read(os.path.join(out, 'assets', 'whomark', 'whomark.js')),
       'rename: hub.js steward pill and whomark.js pill selector still match')
    d2 = os.path.join(t, 'drift', 'site'); shutil.copytree(out, d2)
    r = drift(d2)
    ok(r['status'] == 'OK' and not r['findings'] and not r['warnings'], 'rename: shell_drift still OK (%s)' % r['findings'][:3])
    # topic template (HUB_COPY 4a-4e) renders with a dummy topic; topic text is escaped and never token-expanded
    rr = BR.Renderer(SRC, bp, os.path.join(t, 'tt')).run()
    th = rr.render_topic({'slug': 'tide-pools', 'name': 'Tide <Pools>', 'description': 'Rock pools {{brand.name}}', 'longDescription': 'All about pools.',
                          'goodPosts': 'Photos.', 'offTopic': 'Surfing.', 'rulesShort': 'Be kind.'})
    ok('<h1>Tide &lt;Pools&gt;</h1>' in th and '&#123;&#123;brand.name&#125;&#125;' in th and '{{' not in th, 'topic template: escaped, no token expansion, no leftovers')
    ok(HEAD_RE.match(th) is not None and 'quillnest.example/z/tide-pools/' in th and 'Quillnest Labs, Inc.' in th, 'topic template: strict CSP first, topic URL under the prefix, footer')
    ok(re.search(r'data-topic-state="hidden" hidden', th) and re.search(r'data-profile="[^"]*" hidden', th), 'topic template: empty-state and profile-gated blocks render hidden')
    try:
        rr.render_topic({'slug': 'Bad Slug', 'name': 'x', 'description': 'x', 'longDescription': 'x', 'goodPosts': 'x', 'offTopic': 'x', 'rulesShort': 'x'})
        ok(False, 'topic template: a bad slug is refused')
    except BR.RenderError:
        ok(True, 'topic template: a bad slug is refused')

# renderer refuses gaps
with tempfile.TemporaryDirectory() as t:
    bad = dict(brand); del bad['tagline']
    bp = os.path.join(t, 'b.json'); json.dump(bad, open(bp, 'w'))
    try:
        BR.Renderer(SRC, bp, os.path.join(t, 'o')).run(); ok(False, 'renderer refuses a brand.json missing a used key')
    except BR.RenderError as e:
        ok('tagline' in str(e), 'renderer refuses a brand.json missing a used key (%s)' % e)
    bad = dict(brand, topicPathPrefix='/../')
    json.dump(bad, open(bp, 'w'))
    try:
        BR.Renderer(SRC, bp, os.path.join(t, 'o2')); ok(False, 'renderer refuses a topicPathPrefix outside /x/')
    except BR.RenderError:
        ok(True, 'renderer refuses a topicPathPrefix outside /x/')

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
