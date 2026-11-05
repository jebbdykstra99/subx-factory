#!/usr/bin/env python3
"""Hub (hub/src -> hub/site) and brand/brand.json: render is reproducible, a dummy rename reaches every page with no
brand literal left, every page carries the go-live robots rules (public hub pages indexed, topics hide-until-active) + strict CSP + footer, and tools/shell_drift.py scores the
hub OK with the CSP rule enforced. Offline; temp dirs only (the hub data files are not refetched)."""
import base64, hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import brand_render as BR  # noqa: E402
import byline_allow as BYLINE  # noqa: E402

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
# B2 (Key 2, 2026-11-04): the shell is self-hosted at /shell/<base>/factory.js as a hub-only fork (header line only, new SRI);
# static (noShell) pages: script-src and connect-src are 'self' only (Round 5: no external request).
# HUB SIGN-IN (2026-11-04): the shell page (index.html) carries CSP_AUTH, pinned here source by source. Every origin
# was found by headless Chrome CSP-violation capture of the real sign-in (Firebase Auth popup, App Check reCAPTCHA v3,
# Firestore). Exact files or exact folders only; no wildcard, no bare Google host.
SHELL_REL = 'shell/%s/factory.js' % cfg['shell']['base']
PIN = '/' + SHELL_REL
CDN_PIN = 'https://cdn.jsdelivr.net/gh/%s@%s/shell/%s/factory.js' % (cfg['shell']['repo'], cfg['shell']['sha'], cfg['shell']['base'])
CSP = "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; font-src 'self'"
CSP_AUTH_SCRIPT = ["'self'", 'https://www.gstatic.com/firebasejs/10.12.2/', 'https://www.google.com/recaptcha/api.js',
                   'https://www.gstatic.com/recaptcha/releases/', 'https://apis.google.com/js/api.js',
                   'https://apis.google.com/_/scs/abc-static/']
CSP_AUTH_CONNECT = ["'self'", 'https://subx-skins.web.app', 'https://identitytoolkit.googleapis.com',
                    'https://securetoken.googleapis.com', 'https://firestore.googleapis.com',
                    'https://content-firebaseappcheck.googleapis.com', 'https://www.google.com/recaptcha/']
CSP_AUTH_FRAME = ['https://subx-skins.firebaseapp.com', 'https://www.google.com/recaptcha/']
CSP_AUTH = ("script-src " + ' '.join(CSP_AUTH_SCRIPT) + "; connect-src " + ' '.join(CSP_AUTH_CONNECT) +
            "; frame-src " + ' '.join(CSP_AUTH_FRAME) + "; object-src 'none'; base-uri 'none'; font-src 'self'")
FB_SDK = ['app', 'app-check', 'auth', 'firestore', 'storage']

# ---- brand.json ----
want_keys = ['name', 'legalEntity', 'primaryDomain', 'shortName', 'tagline', 'takedownEmail', 'topicPathPrefix',
             'reviewerLine', 'taglineOptions', 'contactPhone', 'mailingAddress', 'roomNoun', 'topicNoun',
             'disclosureMark', 'nonAffiliation', 'nonAffiliationGov', 'notAdvice', 'footer']
ok(list(brand) == want_keys, 'brand.json has the 18 keys (17 of the brand.json draft plus nonAffiliationGov), in order, and no _draft (%s)' % list(brand))
ok(brand['nonAffiliationGov'] == 'Not affiliated with, endorsed by, or speaking for any government agency.', 'brand.nonAffiliationGov has the exact text')
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
SEED = json.load(open(os.path.join(ROOT, 'topics', 'seed_wave1.json')))
LIVE_TOPICS = [t for t in SEED['topics'] if t['status'] != 'hold']
TOPIC_PAGES = [brand['topicPathPrefix'].strip('/') + '/' + t['slug'] + '/index.html' for t in LIVE_TOPICS]
# go-live 2026-11-04: the public hub pages are indexed; 404, the topic index and every non-active topic stay noindex
PUBLIC_PAGES = ['index.html', 'rooms.html', 'about.html', 'terms.html', 'privacy.html', 'guidelines.html', 'report.html']
NOINDEX_PAGES = ['404.html', topic_index] + TOPIC_PAGES
ok(sorted(pages) == sorted(['index.html', 'rooms.html', 'about.html', topic_index, 'terms.html', 'privacy.html', 'guidelines.html', 'report.html', '404.html'] + TOPIC_PAGES),
   'hub pages: home, rooms, about, topic index, 4 legal, 404 + %d topic pages (%d pages)' % (len(TOPIC_PAGES), len(pages)))
site = json.load(open(os.path.join(SITE, 'site.json')))
sh = site['shell']
no_shell = set(x.lstrip('/') for x in sh.get('noShell', []))
ok(site['siteId'] == 'subx' and site['accountsOpen'] is True and sh['cspRequired'] is True and sh['base'] == cfg['shell']['base'],
   'site.json: siteId subx, accounts open (HUB SIGN-IN), cspRequired true, base = pin base')
ok(site.get('minAge') == 18 and site.get('dms') is False and not (site.get('features') or {}).get('following') and not (site.get('features') or {}).get('notifs')
   and site.get('imageUploads') is False and (site.get('stories') or {}).get('enabled') is False,
   'site.json: hub sign-in only: minAge 18, DMs, following, notifications, uploads and stories stay off')
_man = json.load(open(os.path.join(ROOT, 'shell', cfg['shell']['base'], 'SHELL.json')))['files']['factory.js']
_sb = open(os.path.join(SITE, SHELL_REL), 'rb').read()
_pb = open(os.path.join(ROOT, SHELL_REL), 'rb').read()
_fsha = hashlib.sha256(_sb).hexdigest()
_fsri = 'sha384-' + base64.b64encode(hashlib.sha384(_sb).digest()).decode()
ok(sh.get('fork') is True and sh.get('file') == SHELL_REL and sh.get('sha256') == _fsha and sh.get('exception') == 'E21' and 'header' in sh.get('reason', ''),
   'site.json: the self-hosted shell is a declared hub-only fork (file, fork sha256, EXCEPTIONS.md E21, header-only reason)')
_e21 = [l for l in open(os.path.join(ROOT, 'EXCEPTIONS.md'), encoding='utf-8').read().splitlines() if l.startswith('| E21 | hub (subx.it) |')]
ok(len(_e21) == 1 and 'hub-only fork' in _e21[0] and 'header' in _e21[0] and _fsri in _e21[0] and 'jebbdykstra99' not in _e21[0],
   'EXCEPTIONS.md E21 describes the hub-only header fork with its new SRI')
# the pinned source is verified first (SRI, sha256, size = config.json + SHELL.json), and is the bytes at the pinned commit
_psri = 'sha384-' + base64.b64encode(hashlib.sha384(_pb).digest()).decode()
ok(_psri == cfg['shell']['integrity'] == _man['integrity'] and hashlib.sha256(_pb).hexdigest() == _man['sha256'] and len(_pb) == _man['bytes'],
   'pinned shell/%s: sha384 = config.json integrity = SHELL.json, sha256 and size = SHELL.json' % SHELL_REL)
_pinned = subprocess.run(['git', '-C', ROOT, 'show', '%s:%s' % (cfg['shell']['sha'], SHELL_REL)], capture_output=True)
ok(_pinned.returncode != 0 or _pinned.stdout == _pb, 'pinned shell = the bytes at the pinned commit %s (when that commit is in the clone)' % cfg['shell']['sha'][:7])
# the fork differs from the pin by exactly one line: the header source line
_pl, _fl = _pb.split(b'\n'), _sb.split(b'\n')
_dl = [i for i in range(max(len(_pl), len(_fl))) if i >= len(_pl) or i >= len(_fl) or _pl[i] != _fl[i]]
_hdr = (' * Source: SubX shared shell %s (hub fork, header only)' % cfg['shell']['base']).encode()
ok(len(_pl) == len(_fl) and len(_dl) == 1 and b'github.com/jebbdykstra99/subx-factory' in _pl[_dl[0]] and _pl[_dl[0]].lstrip().startswith(b'*') and _fl[_dl[0]] == _hdr,
   'hub fork = pinned shell with exactly one line changed (header source line -> %r) (diff lines %s)' % (_hdr.decode(), [i + 1 for i in _dl][:5]))
ok(_sb.replace(_hdr, _pl[_dl[0]] if _dl else b'', 1) == _pb, 'hub fork: undoing the one header substitution gives the pinned bytes exactly')
ok(_fsri != cfg['shell']['integrity'] and len(_sb) == len(_pb) - len(_pl[_dl[0]] if _dl else b'') + len(_hdr), 'hub fork has its own SRI (not the pin SRI) and the expected size')
ok(BR.Renderer(SRC, os.path.join(ROOT, 'brand', 'brand.json'), SITE).shell_bytes() == (_sb, _fsha, _fsri), 'renderer shell_bytes() = (fork bytes, fork sha256, fork SRI)')
_jb = [f for f in files(SITE) if 'jebbdykstra99' in open(os.path.join(SITE, f), encoding='utf-8', errors='replace').read()]
ok(not _jb and 'jebbdykstra99' not in open(os.path.join(ROOT, 'hub', 'firebase.json')).read(), 'no jebbdykstra99 anywhere in rendered hub output or hub/firebase.json (%s)' % _jb[:3])
ok(not any('jsdelivr' in open(os.path.join(SITE, f), encoding='utf-8', errors='replace').read() for f in files(SITE) if f.endswith('.html')), 'no page references jsDelivr')
leg = json.load(open(os.path.join(ROOT, 'tools', 'csp_legacy_rooms.json')))['rooms']
ok('subx' not in leg and 'hub' not in leg, 'the hub is not on the CSP legacy list')
ok(sh.get('recaptcha') is True and sh.get('googleSignIn') is True, 'site.json shell: recaptcha and googleSignIn opt-ins set (App Check reCAPTCHA v3, Google popup gapi)')
ok(not [p for p in pages if p != 'index.html' and re.search(r'(google|gstatic)\.com/recaptcha', read(os.path.join(SITE, p)))], 'no static page loads reCAPTCHA (only the shell page CSP lists it)')
ok(not [p for p in pages if p not in ('index.html', 'privacy.html') and 'recaptcha' in read(os.path.join(SITE, p)).lower()], 'no static page but privacy mentions reCAPTCHA (privacy names it under abuse prevention)')
ok('index.html' not in no_shell and no_shell == set(pages) - {'index.html'}, 'index.html runs the shell; every other page is a declared noShell static page')

HEAD_RE = re.compile(r'^<!DOCTYPE html>\s*<html lang="en">\s*<head>\s*<meta charset="UTF-8">\s*<meta http-equiv="Content-Security-Policy" content="([^"]*)">', re.I)
for p in pages:
    h = read(os.path.join(SITE, p))
    m = HEAD_RE.match(h)
    want_csp = CSP_AUTH if p == 'index.html' else CSP
    ok(m is not None and m.group(1) == want_csp, '%s: meta CSP is the first element after charset, http-equiv exact, %s policy' % (p, 'exact auth' if p == 'index.html' else 'strict'))
    if m:
        c = m.group(1)
        ok(all(32 <= ord(ch) < 127 for ch in c) and ',' not in c and (p == 'index.html' or c.split(';')[0].split() == ['script-src', "'self'"]), '%s: CSP is ASCII, no commas, script-src is self only on static pages' % p)
        ok('*' not in c and ' https: ' not in c + ' ' and 'unsafe' not in c and "'nonce" not in c, '%s: CSP has no wildcard, scheme source, unsafe-* or nonce' % p)
    ok(h.count('Content-Security-Policy') == 1, '%s: exactly one CSP meta' % p)
    want_robots = 'index,follow' if p in PUBLIC_PAGES else 'noindex,nofollow'
    ok(re.findall(r'<meta name="robots" content="([^"]*)">', h) == [want_robots], '%s: exactly one robots meta, %s' % (p, want_robots))
    canon = 'https://%s/%s' % (brand['primaryDomain'], p[:-len('index.html')] if p.endswith('index.html') else p)
    ok(re.findall(r'<link rel="canonical" href="([^"]*)">', h) == [canon], '%s: canonical %s' % (p, canon))
    ok('preview-banner' not in h and 'Not public and not indexed' not in h, '%s: no preview banner' % p)
    fm = re.search(r'<footer class="legal-footer"[^>]*>(.*?)</footer>', h, re.S)
    ok(fm is not None and brand['legalEntity'] in fm.group(1) and brand['takedownEmail'] in fm.group(1) and brand['nonAffiliation'] in fm.group(1),
       '%s: legal footer with %s, the takedown email and the non-affiliation line' % (p, brand['legalEntity']))
    pins = re.findall(r'<script\b[^>]*\bsrc="([^"]*factory[^"]*)"[^>]*>', h)
    if p == 'index.html':
        tag = re.search(r'<script src="%s" integrity="%s" crossorigin="anonymous" data-site="/site\.json\?v=[0-9a-f]{10}"></script>' % (re.escape(PIN), re.escape(_fsri)), h)
        ok(tag is not None and pins == [PIN], 'index.html: the self-hosted shell (SRI, crossorigin, data-site) and no other factory script')
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
# Room taglines + rail snippets: same filter (dash / "Seed") plus "pending", "TODO", "Content DB"; failing ones ship as ""
src_rooms = json.load(open(os.path.join(ROOT, 'hub', 'src', 'rooms.json'), encoding='utf-8'))
tag_of = {r['room']: r.get('tagline') for r in src_rooms['rooms']}
for room in ('airlineschat', 'amachat', 'behindtheblackwall'):
    ok(BH.tagline_rule(tag_of[room]) is not None, 'tagline_rule drops the %s tagline' % room)
for t, want in (('Personal archive. TODO', 'placeholder'), ('Copy pending review', 'placeholder'), ('Seeded room', 'seed_prefix'),
                ('Nothing but BART.', None), ('Todo el mundo.', None)):
    ok(BH.tagline_rule(t) == want, 'tagline_rule(%r) == %r' % (t, want))
ok(BH.safe_tagline('A \u2014 B') == '' and BH.safe_tagline('Hoods up.') == 'Hoods up.', 'safe_tagline blanks a failing tagline, keeps a clean one verbatim')
bad_tags = BH.bad_taglines(src_rooms)
shipped = [x.get('tagline', '') for x in rooms['rooms']] + [x.get('snippet', '') for x in site['rail']['outbound']]
ok(all(t == '' or BH.tagline_rule(t) is None for t in shipped), 'hub/site rooms.json taglines + site.json rail snippets all pass tagline_rule')
ok(all(t == '' or t in tag_of.values() for t in shipped), 'shipped taglines are verbatim room copy (never rewritten)')
leak = [(f, b) for f in files(SITE) if f.endswith(TEXT) for b in bad_tags if b in read(os.path.join(SITE, f))]
ok(bad_tags and not leak, 'no failing room tagline appears anywhere in hub/site (%d checked, leaks %s)' % (len(bad_tags), leak[:3]))
ok(all(x['name'] and x['domain'] for x in rooms['rooms']), 'rooms keep name + link')
ok(not [it['postId'] for it in src_hl['items'] if BH.quotes_bad_tagline(it['text'], bad_tags)], 'highlights.json: no item quotes a failing tagline')
ok("(r.tagline ? '<p>' + esc(r.tagline) + '</p>' : '')" in read(os.path.join(SITE, 'hub.js')), 'hub.js: a room with no tagline renders no empty tagline line')
# Key 1 edit E2: sign-up consent wording
ok('(preview stubs, not final counsel)' not in idx and '(preview drafts)' not in idx and idx.count('Privacy Policy</a>.</span>') == 2,
   'index.html: both sign-up consent lines link Terms + Privacy with no preview/draft qualifier')
# Key 1 edit E1 (2026-11-04): DM placeholder is exactly the launch line, no internal dev note. PR #43 (Key 1 E1) removes
# the shell Chat overlay from the hub (Chat hands off to each room), so the placeholder may also be absent.
ok(re.findall(r'<div class="chat-placeholder-sub">([^<]*)</div>', idx) in (['Direct messages are not live yet.'], []), 'index.html: DM placeholder, if present, reads exactly "Direct messages are not live yet."')
for p in pages:
    vis = re.sub(r'<!--.*?-->', '', re.sub(r'<(script|style)\b.*?</\1>', '', read(os.path.join(SITE, p)), flags=re.S), flags=re.S)
    vis = re.sub(r'<[^>]+>', ' ', vis)
    ok(not re.search(r'site\.json|DMs graph|\bstubs?\b|\bTODO\b|FIXME|not a real inbox|[Ss]ample thread', vis), '%s: no internal dev note in visible text' % p)
# B3 (Key 2): no Report-button promise the hub cannot keep
rp = read(os.path.join(SITE, 'report.html'))
RL = 'Use the Report link on the post in its room, or email <a data-takedown href="mailto:%s">%s</a>.' % (brand['takedownEmail'], brand['takedownEmail'])
ok(rp.count(RL) == 2 and 'Report button' not in rp, 'report.html: both Report-button lines read "Use the Report link on the post in its room, or email takedown@subx.it."')
# W3 (Key 2): the profile Sign in button is still hidden if accounts are ever closed again (html.acc-closed)
_hcss = read(os.path.join(SITE, 'hub.css'))
ok(re.search(r'\.acc-closed #profile-signin-prompt-btn \{ display: none !important; \}', _hcss) is not None,
   'hub.css: #profile-signin-prompt-btn hidden under html.acc-closed (kill switch kept)')
ok('Members sign in here. Guest is browse-only.' in idx and 'Sign-in opens soon' not in idx and 'Sign-in is closed while the hub is in preview' not in idx and '<span>Read-only</span>' not in idx,
   'index.html: sign-in wording reuses the rooms ("Members sign in here. Guest is browse-only."), no "opens soon" or Read-only claim')
# HUB SIGN-IN: a visible Sign in / Join entry on the home page (outside the drawer, so it shows at 390px), plus the shell's own
# #sidebar-auth in the left nav / mobile drawer. The header button only clicks the shell's #auth-signin (one auth flow).
ok(idx.count('id="hub-join-btn"') == 1 and re.search(r'<button type="button" class="hub-cta hub-join" id="hub-join-btn" aria-haspopup="dialog">Sign in / Join</button>', idx) is not None,
   'index.html: one header Sign in / Join button (#hub-join-btn)')
ok(idx.index('id="hub-join-btn"') > idx.index('<main class="main">') and idx.count('id="sidebar-auth"') == 1 and idx.index('id="sidebar-auth"') < idx.index('</aside>'),
   'index.html: Sign in / Join sits in the page header (visible without the drawer); #sidebar-auth stays in the left nav / mobile drawer')
ok(not re.search(r'#sidebar-auth|#cv-auth-overlay', re.sub(r'/\*.*?\*/', '', _hcss, flags=re.S)), 'hub.css: #sidebar-auth and the sign-in modal (#cv-auth-overlay) are no longer hidden')
ok('.acc-closed .hub-join' in _hcss and '.hub-join[hidden]' in _hcss, 'hub.css: the header Sign in / Join hides when accounts close or once signed in')
_hjs = read(os.path.join(SITE, 'hub.js'))
ok("getElementById('auth-signin')" in _hjs and 'b.click()' in _hjs and 'MutationObserver' in _hjs and 'signInWith' not in _hjs and 'firebase' not in _hjs.lower().replace('no writes of', ''),
   'hub.js: Sign in / Join clicks the shell #auth-signin, no auth code of its own')
_sc = read(os.path.join(SITE, 'index.html'))
_fb_tags = re.findall(r'<script src="https://www\.gstatic\.com/firebasejs/10\.12\.2/firebase-([a-z-]+)-compat\.js" integrity="(sha384-[A-Za-z0-9+/=]+)" crossorigin="anonymous"></script>', _sc)
ok([t[0] for t in _fb_tags] == FB_SDK and _sc.index('firebase-storage-compat.js') < _sc.index('/shell/'),
   'index.html: Firebase compat 10.12.2 app, app-check, auth, firestore, storage load before the shell, each with SRI')
# launch copy: no preview / draft wording left in any rendered page (CSS class names like compose-image-preview excepted)
for p in pages:
    vis = re.sub(r'<(script|style)\b.*?</\1>', '', read(os.path.join(SITE, p)), flags=re.S)
    vis = re.sub(r'(class|id)="[^"]*"', '', vis)
    ok(not re.search(r'\bpreview\b|\bdraft', vis, re.I), '%s: no preview/draft wording' % p)
KICK1 = ('The hub takes sign-in but no posts: you can sign in with the same account the rooms use, and posts, replies, '
         'stories, and messages stay in each room. The hub does not send the visit beacon. Highlights link to the original '
         'post in its room, where that room\u2019s own terms apply.')
for p in ('terms.html', 'privacy.html', 'guidelines.html', 'report.html'):
    lp = read(os.path.join(SITE, p))
    ok('<p class="legal-kicker">Effective November 4, 2026. ' + KICK1 + '</p>' in lp and 'Draft for review' not in lp and 'The hub is read-only' not in lp, '%s: effective November 4, 2026, hub sign-in kicker' % p)
pv = read(os.path.join(SITE, 'privacy.html'))
ok('The pages are hosted on Firebase Hosting (Google), and sign-in,' in pv and 'hosted on GitHub Pages' not in pv, 'privacy.html: hosting line names Firebase Hosting (Google)')
# CLO edits 2026-11-04 (3)-(5): second kickers and the Processors bullet, exact
KICK2 = {'guidelines.html': 'Community guidelines', 'report.html': 'Report / takedown request',
         'terms.html': 'Governing law: State of California, United States of America', 'privacy.html': 'Governing law: State of California, United States of America'}
for p, k in KICK2.items():
    kk = re.findall(r'<p class="legal-kicker">([^<]*)</p>', read(os.path.join(SITE, p)))
    ok(len(kk) == 2 and kk[0].startswith('Effective November 4, 2026. ') and kk[1] == k, '%s: kickers = effective Nov 4, 2026 + exactly %r (%s)' % (p, k, kk[1:]))
    ok('Effective October 22' not in read(os.path.join(SITE, p)) and 'Effective on launch' not in read(os.path.join(SITE, p)), '%s: no stale effective date' % p)
PROC = ("<li><strong>Processors</strong>: service providers that host, deliver, or secure the Service (Google Firebase / Google Cloud, "
        "including Firebase Hosting; GoDaddy, for domain DNS) under contracts or terms that limit use of the data.</li>")
ok(pv.count(PROC) == 1 and pv.count('<strong>Processors</strong>') == 1 and 'Cloudflare' not in pv and 'GitHub Pages' not in pv, 'privacy.html: Processors bullet is exactly the CLO text, jsDelivr clause removed (no GitHub Pages, no Cloudflare)')
ok('jsDelivr' not in pv, 'privacy.html: jsDelivr is no longer named (B2 self-hosts the shell)')
# HUB SIGN-IN: privacy discloses hub accounts (uid, display name, provider profile basics, follows and messages), same
# retention as rooms, the rooms' age line (minAge 18) and handle sentence, reused word for word
_bn = brand['name']
for _need in ('<li><strong>Hub accounts</strong>: signing in on the hub uses the same %s account as the rooms.' % _bn,
              'we store your account ID (<code>uid</code>), your display name,',
              'the basic profile fields your sign-in provider shares with us (for Google: your name, email address, and profile photo link).',
              'Follows and direct messages you make with that account in a room are stored with your account. Follows you make on the hub stay in your browser only (see Hub follows below).',
              'password (our sign-in provider stores it only as a hash)',
              'For abuse prevention, App Check uses Google reCAPTCHA, which runs on the pages where you can sign in',
              '<p id="hub-account-delete"><strong>Deleting your hub account:</strong> there is no in-app delete button. Email <a data-takedown href="mailto:%s">' % brand['takedownEmail'],
              'Hub account data, including follows and messages made with a hub account in a room, is kept the same way as room account data. Follows made on the hub stay in your browser (see Hub follows).',
              'the 25-month visitor-ID limit above applies.',
              'Your public handle is something you choose. We do not make it from your email address, and we do not show your email address to other users.',
              '<p>You must be at least 18 to have an account on %s. The Service is not directed to children, and we do not knowingly collect personal information from anyone under 18, including children under 13. If we learn that we have, we close the account and delete the information, except what the law requires us to keep. If you believe we have information about someone under 18, contact us at <a data-takedown href="mailto:%s">%s</a>.</p>' % (_bn, brand['takedownEmail'], brand['takedownEmail'])):
    ok(pv.count(_need) == 1, 'privacy.html (hub sign-in): %r' % _need[:70])
ok('not directed to anyone under 18' not in pv and 'read-only index' not in pv, 'privacy.html: old age line and read-only claim gone')
ok('the same way as in the rooms.' not in pv and 'auth provider' not in pv, 'privacy.html: old hub DM line and "auth provider" wording gone')
ok('made with a hub account, is kept' not in pv, 'privacy.html: old retention line (no room/hub split) gone')
_ix = read(os.path.join(SITE, 'index.html'))
ok(('<meta name="description" content="%s is a home for small, single-topic %s. Highlights from live %s, each linking back to its %s. One %s account works on the hub and in every %s.">'
    % (_bn, brand['roomNoun']['many'], brand['roomNoun']['many'], brand['roomNoun']['one'], _bn, brand['roomNoun']['one'])) in _ix and 'Read-only.' not in _ix,
   'index.html: meta description names the one account, no "Read-only."')
ok(('id="hub-compose-text" rows="2" maxlength="280" placeholder="Post in a %s."' % brand['roomNoun']['one']) in _ix, 'index.html: hub composer placeholder is "Post in a %s."' % brand['roomNoun']['one'])
ok(not re.search('[\u2013\u2014]', re.sub(r'<[^>]+>', '', pv.split('Hub accounts', 1)[1].split('</li>', 1)[0])), 'privacy.html: no em or en dash in the hub accounts bullet')
# HUB SIGN-IN (replaces CLO note (a)): only the shell page loads the Firebase SDK; static pages cannot
ok(not [p for p in pages if p != 'index.html' and re.search(r'<script[^>]+(gstatic|firebase|googleapis|apis\.google)', read(os.path.join(SITE, p)), re.I)], 'no static page loads the Firebase / Google auth SDK')
ok(not re.search(r'gstatic|googleapis|apis\.google|firebase', CSP.split('script-src', 1)[1].split(';')[0]), 'static CSP script-src cannot load the Firebase / Google auth SDK')
_dirs = dict((d.split()[0], d.split()[1:]) for d in CSP_AUTH.split('; '))
ok(list(_dirs) == ['script-src', 'connect-src', 'frame-src', 'object-src', 'base-uri', 'font-src'] and _dirs['object-src'] == ["'none'"] and _dirs['base-uri'] == ["'none'"]
   and 'default-src' not in _dirs and 'worker-src' not in _dirs, 'CSP_AUTH: exact directive list, object-src and base-uri none')
ok(all(x == "'self'" or (x.startswith('https://') and '*' not in x and re.fullmatch(r'https://[a-z0-9.-]+\.[a-z]+(/[A-Za-z0-9._/-]*)?', x)) for d in ('script-src', 'connect-src', 'frame-src') for x in _dirs[d]),
   'CSP_AUTH: every source is self or an exact https origin / path (no wildcard, no scheme source)')
ok(all(x == "'self'" or x.endswith('.js') or x.endswith('/') and x.count('/') >= 4 for x in _dirs['script-src']),
   'CSP_AUTH script-src: exact files or exact path folders only (no bare Google host)')
ok(BR.CSP_AUTH == CSP_AUTH and BR.CSP_STATIC == CSP, 'tools/brand_render.py CSP_AUTH / CSP_STATIC = the allowlist pinned in this test')
for p in ('about.html', 'rooms.html', '404.html'):
    ok('<p class="legal-kicker">%s</p>' % brand['name'] in read(os.path.join(SITE, p)), '%s: kicker without Preview' % p)
ok('<p class="legal-kicker">%s · Coming soon</p>' % brand['name'] in read(os.path.join(SITE, topic_index)), 'topic index: kicker without Preview')
ok(len(rooms['rooms']) > 0 and [x['url'] for x in site['rail']['outbound']] == ['https://%s/' % x['domain'] for x in rooms['rooms']], 'site.json rail.outbound mirrors rooms.json')

# WHOMARK legend: the three final-v4.1 tiers (AI steward posts are AI-made) on about + topic index
for p in ('about.html', topic_index):
    h = read(os.path.join(SITE, p))
    rows = re.findall(r'<tr>\s*<th scope="row">(.*?)</th>', h, re.S)
    labels = [re.sub(r'<[^>]+>', '', x).strip() for x in rows]
    ok(labels == ['Human-made', 'AI-made', 'Human + AI'], '%s: WHOMARK legend rows (%s)' % (p, labels))
tiers = set(json.load(open(os.path.join(SITE, 'assets', 'whomark', 'config.json')))['tiers'])
used = set(re.findall(r'whomark--(human|ai|hybrid)\b', read(os.path.join(SITE, 'about.html'))))
ok(used == tiers, 'legend uses only real whomark tiers (%s of %s)' % (sorted(used), sorted(tiers)))

# topics held for the topic-layer PR
tdir_ = os.path.join(SITE, brand['topicPathPrefix'].strip('/'))
ok(files(tdir_) == sorted(['index.html'] + [t['slug'] + '/index.html' for t in LIVE_TOPICS]), 'topic folder = index + one page per non-HOLD seed topic')
ok(len(SEED['topics']) == 52 and len(LIVE_TOPICS) == 51 and [t['slug'] for t in SEED['topics'] if t['status'] == 'hold'] == ['grief'], 'seed: 52 topics, 51 rendered, grief is the only HOLD')
ok(not os.path.exists(os.path.join(tdir_, 'grief')), 'HOLD topic grief is not rendered')
ok(all(t['status'] == 'hidden' for t in LIVE_TOPICS), 'every rendered topic is hidden at go-live')
ok(cfg['topics']['hubNoindex'] is False, 'config.json topics.hubNoindex is false (hub-wide noindex lifted)')
for t in LIVE_TOPICS:
    pg = brand['topicPathPrefix'].strip('/') + '/' + t['slug'] + '/index.html'
    h = read(os.path.join(SITE, pg))
    ok('<meta name="robots" content="noindex,nofollow">' in h, '%s: noindex,nofollow' % pg)
    ok('<!--' not in h and '{{' not in h, '%s: no HTML comments or tokens left' % pg)
    ok('data-topic-state="not-live"' in h and 'Not live yet.' in h and 'Start the first thread' not in h and 'open to read and post' not in h,
       '%s: shows the not-live-yet state only' % pg)
    ok('Also reachable at' not in h and not any(d in h for d in t['doorwayDomains']), '%s: no doorway line or legacy domain tonight' % pg)
    ok(('21+ only.' in h) == (t.get('legalProfile') == 'alcohol-21') and (brand['notAdvice'] in h) == (t.get('legalProfile') in ('sensitive-18', 'alcohol-21')),
       '%s: legal-profile lines match %s' % (pg, t.get('legalProfile')))
    ok('<title>%s · %s</title>' % (BR.html_attr(t['title']), brand['name']) in h and BR.html_attr(t['description']) in h, '%s: title and description from the seed' % pg)
    ok(pg in site['shell']['noShell'], '%s is listed in shell.noShell' % pg)
    wh = re.search(r'<p class="topic-where">([^<]*)', h)
    ok(wh is not None and wh.group(1).startswith('A %s %s ' % (brand['name'], brand['topicNoun']['one'])) and brand['roomNoun']['one'] not in wh.group(1).lower(),
       '%s: header calls it a %s, not a %s' % (pg, brand['topicNoun']['one'], brand['roomNoun']['one']))
    ok(('About this %s' % brand['roomNoun']['one']) not in h, '%s: no "About this %s"' % (pg, brand['roomNoun']['one']))
    ok(('Browse %s' % brand['roomNoun']['many']) in h, '%s: live-rooms link keeps %s' % (pg, brand['roomNoun']['many']))
sm = read(os.path.join(SITE, 'sitemap.xml'))
locs = re.findall(r'<loc>([^<]*)</loc>', sm)
want_locs = sorted('https://%s/%s' % (brand['primaryDomain'], '' if p == 'index.html' else p) for p in PUBLIC_PAGES)
ok('<urlset' in sm and sorted(locs) == want_locs, 'sitemap.xml lists exactly the 7 public hub pages (%s)' % locs)
ok(not [u for u in locs if brand['topicPathPrefix'] in u] and not [u for u in locs if '404' in u], 'sitemap.xml lists no topic page, no topic index and no 404 while no topic is active')
ok(all('<meta name="robots" content="noindex,nofollow">' in read(os.path.join(SITE, f)) for f in NOINDEX_PAGES), 'hide-until-active: 404, topic index and every hidden topic stay noindex,nofollow')
ok(all('<meta name="robots" content="index,follow">' in read(os.path.join(SITE, f)) for f in PUBLIC_PAGES), 'public hub pages are index,follow')
ok(not any('preview-banner' in read(os.path.join(SITE, f)) for f in files(SITE) if f.endswith(TEXT) and f != SHELL_REL) and not os.path.exists(os.path.join(SRC, 'partials', 'banner.html')),
   'no preview banner markup or style anywhere in hub/site; banner partial removed')
rt = read(os.path.join(SITE, 'robots.txt'))
groups = [g for g in re.split(r'\n\s*\n', rt) if 'User-agent' in g]
star = [g for g in groups if re.search(r'^User-agent: \*$', g, re.M)]
ok(len(star) == 1 and 'Allow: /' in star[0] and 'Disallow' not in star[0], 'robots.txt: User-agent * may crawl (no Disallow), so noindex metas on topic pages are readable')
ok(not re.search(r'^Disallow: %s' % re.escape(brand['topicPathPrefix']), rt, re.M), 'robots.txt does not disallow the topic path (crawlers must see the topic noindex)')
TRAIN = ('GPTBot', 'ClaudeBot', 'anthropic-ai', 'Google-Extended', 'Applebot-Extended', 'CCBot', 'Bytespider', 'Meta-ExternalAgent')
ANSWER = ('OAI-SearchBot', 'ChatGPT-User', 'PerplexityBot', 'Claude-SearchBot')
ua = lambda g: re.findall(r'^User-agent: (\S+)$', g, re.M)
ai = [g for g in groups if 'GPTBot' in ua(g)]
ok(len(ai) == 1 and sorted(ua(ai[0])) == sorted(TRAIN) and re.search(r'^Disallow: /$', ai[0], re.M) and 'Allow' not in ai[0].replace('Disallow', ''),
   'robots.txt: AI training crawlers stay fully disallowed (%s)' % ', '.join(TRAIN))
ans = [g for g in groups if 'OAI-SearchBot' in ua(g)]
ok(len(ans) == 1 and sorted(ua(ans[0])) == sorted(ANSWER) and re.search(r'^Allow: /$', ans[0], re.M) and 'Disallow' not in ans[0],
   'robots.txt: search/answer agents allowed (%s)' % ', '.join(ANSWER))
ok(all(len([g for g in groups if b in ua(g)]) == 1 for b in TRAIN + ANSWER), 'robots.txt: every named agent is in exactly one group')
ok(re.search(r'^Sitemap: https://%s/sitemap\.xml$' % re.escape(brand['primaryDomain']), rt, re.M) is not None, 'robots.txt names the sitemap on the primary domain')
ll = read(os.path.join(SITE, 'llms.txt'))
ok('robots.txt disallows all crawling' not in ll and 'pages are marked noindex' not in ll and 'noindex until they are active' in ll, 'llms.txt describes the go-live crawl policy')
pol = [l for l in ll.splitlines() if l.startswith('- robots.txt allows')]
ok(len(pol) == 1 and all(b in pol[0].split('disallows')[0] for b in ANSWER) and all(b in pol[0].split('disallows')[1] for b in TRAIN),
   'llms.txt crawler policy matches robots.txt (answer agents allowed, training crawlers disallowed)')
# hide-until-active holds through the renderer with today's config (hub-wide noindex off)
rr_live = BR.Renderer(SRC, BRAND, tempfile.mkdtemp())
rr_live.run()
_row = dict(LIVE_TOPICS[0])
ok('content="noindex,nofollow"' in rr_live.render_topic(dict(_row, status='hidden')) and 'content="noindex,nofollow"' in rr_live.render_topic(dict(_row, status='eligible'))
   and 'content="noindex,nofollow"' in rr_live.render_topic(dict(_row, status='quiet')) and 'content="noindex,nofollow"' in rr_live.render_topic(dict(_row, status='archived'))
   and 'content="index,follow"' in rr_live.render_topic(dict(_row, status='active')), 'live config: only an active topic renders index,follow')
ok('/t/' + _row['slug'] + '/' in rr_live.sitemap([dict(_row, status='active')]) and '/t/' + _row['slug'] + '/' not in rr_live.sitemap([dict(_row, status='hidden')]),
   'live config: an active topic joins the sitemap, a hidden one never does')
shutil.rmtree(rr_live.out, ignore_errors=True)
# rollback switch: hubNoindex true puts every page back under noindex with an empty sitemap
with tempfile.TemporaryDirectory() as t:
    src2 = os.path.join(t, 'src'); shutil.copytree(SRC, src2)
    c2 = json.load(open(os.path.join(src2, 'config.json'))); c2['topics']['hubNoindex'] = True
    json.dump(c2, open(os.path.join(src2, 'config.json'), 'w'))
    BR.render(src=src2, out=os.path.join(t, 'out'))
    outp = [f for f in BR.files_under(os.path.join(t, 'out')) if f.endswith('.html')]
    ok(all('content="noindex,nofollow"' in read(os.path.join(t, 'out', f)) for f in outp) and '<url>' not in read(os.path.join(t, 'out', 'sitemap.xml')),
       'rollback: hubNoindex true = every page noindex,nofollow and an empty sitemap')
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
SELF_SHELL = os.path.abspath(os.path.join(SITE, SHELL_REL))
for p in scan_files():
    if os.path.abspath(p) in (os.path.abspath(__file__), SELF_SHELL):
        continue
    t = read(p) if not p.endswith('.png') else ''
    # Decision 2026-11-05: author bylines ("By Jebb Dykstra") are allowed; mask them
    # before the private-name FORBID so operator/meta/JSON-LD hits still fail.
    t = BYLINE.mask_allowed_bylines(t)
    for rx in FORBID:
        for m in rx.finditer(t):
            hits.append('%s: %s' % (os.path.relpath(p, ROOT), m.group(0)))
ok(not hits, 'no private names, emails, 310 numbers, registered-agent city or internal codes in the hub, brand or renderer (%s)' % hits[:5])
# Decision 2026-11-05: byline allowlist: byline passes, operator/meta still fail
ok(BYLINE.is_name_clean('<p class="byline"><em>By Jebb Dykstra, Juno, Vesta and Iris</em></p>'),
   'byline allowlist: class=byline "By Jebb Dykstra, Juno, Vesta and Iris" passes')
ok(not BYLINE.is_name_clean('<meta name="author" content="Jebb Dykstra">'),
   'byline allowlist: meta author with Jebb still fails')
ok(not BYLINE.is_name_clean('{"publisher":{"name":"Jebb Dykstra"}}'),
   'byline allowlist: JSON-LD publisher with Jebb still fails')
ok(not BYLINE.is_name_clean('<p>operated by Jebb Dykstra</p>'),
   'byline allowlist: operator line with Jebb still fails')
ok(not BYLINE.is_name_clean('<footer class="byline">Operated By Jebb Dykstra</footer>')
   and not BYLINE.is_name_clean('<div><p>By Jebb Dykstra</p> Reviewer: By Jebb Dykstra</div>')
   and not BYLINE.is_name_clean('<p class="not-byline">By Jebb Dykstra</p>'),
   'byline allowlist: footer/div/not-byline leaks still fail (Key 1 E1-E2)')
# the self-hosted hub fork keeps upstream code: its only owner-handle string is the functional reserved-handle regex "jebb"
_sh = [m.group(0) for rx in FORBID[:1] + [re.compile('jebbdykstra99')] for m in rx.finditer(read(SELF_SHELL))]
ok(_sh == ['jebb'] and '(admin|moderator|official|subx|jebb)' in read(SELF_SHELL) and not [m for rx in FORBID[1:] for m in rx.finditer(read(SELF_SHELL))],
   'self-hosted hub fork: only the reserved-handle regex "jebb" (functional); no repo path, no other private string (%s)' % _sh)
# Key 2 B1: never claim affiliation with X ("Affiliated with X" only ever as "Not affiliated with X")
AFFIL = re.compile(r'(?<!not )affiliated with x\b', re.I)
bad = []
for f in files(SITE):
    if f.endswith(TEXT):
        t = re.sub(r'<[^>]+>', ' ', read(os.path.join(SITE, f)))
        if 'Affiliated with X Corp.' in t or AFFIL.search(re.sub(r'\s+', ' ', t)):
            bad.append(f)
ok(not bad, 'no rendered page says "Affiliated with X" without "Not " before it (%s)' % bad)
ok('Affiliated with X Corp.' not in read(os.path.join(SITE, 'about.html')) and '<li>%s</li>' % brand['nonAffiliation'] in read(os.path.join(SITE, 'about.html')),
   'about.html: the "is not" list uses brand.nonAffiliation only')
# Key 2 C5: the disclosure mark comes from brand.json, never typed into hub sources
lit = [n for d in ('templates', 'partials') for n in os.listdir(os.path.join(SRC, d))
       if n.endswith(TEXT) and 'WHOMARK' in read(os.path.join(SRC, d, n))]
ok(not lit, 'hub/src templates + partials: no literal WHOMARK (use {{brand.disclosureMark}}) (%s)' % lit)
ok('## Provenance labels (%s)' % brand['disclosureMark'] in read(os.path.join(SITE, 'llms.txt')), 'llms.txt: provenance heading renders brand.disclosureMark')
# Key 2 C6: fonts self-hosted (OFL), no Google Fonts requests, font-src 'self'
gf = [f for f in files(SITE) if f.endswith(TEXT) and re.search(r'fonts\.(googleapis|gstatic)\.com', read(os.path.join(SITE, f)))]
ok(not gf, 'hub/site: no Google Fonts links (%s)' % gf)
hcss = read(os.path.join(SITE, 'hub.css'))
furls = re.findall(r"url\((/assets/fonts/[^)?]+\.woff2)\?v=[0-9a-f]{10}\)", hcss)
ok(len(furls) == 6 and all(os.path.isfile(os.path.join(SITE, u.lstrip('/'))) for u in furls), 'hub.css: 6 self-hosted woff2 faces, all present')
ok(all(os.path.isfile(os.path.join(SITE, 'assets', 'fonts', 'OFL-%s.txt' % n)) and 'SIL Open Font License' in read(os.path.join(SITE, 'assets', 'fonts', 'OFL-%s.txt' % n))
       for n in ('Inter', 'Newsreader')), 'assets/fonts: OFL 1.1 license files ship with the fonts')
ok("font-src 'self'" in json.dumps(json.load(open(os.path.join(ROOT, 'hub', 'firebase.json')))), "firebase.json header CSP: font-src 'self'")
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
    ok(r['status'] == 'FORK' and r['layers'].get('forkDiffLines') == 2 and not r['findings'] and not r['warnings'], 'shell_drift hub/site = FORK (hub-only header fork: 2 diff lines), no findings or warnings, CSP enforced (%s %s)' % (r['findings'][:3], r['warnings'][:3]))
    fb = json.load(open(os.path.join(ROOT, 'hub', 'firebase.json')))
    shutil.copy(os.path.join(ROOT, 'hub', 'firebase.json'), os.path.join(d, 'firebase.json'))
    r = drift(d)
    ok(r['status'] == 'FORK' and r['layers'].get('forkDiffLines') == 2 and not r['findings'] and not r['warnings'], 'shell_drift hub/site + hub/firebase.json headers = FORK (%s %s)' % (r['findings'][:3], r['warnings'][:3]))
    hs = fb['hosting']
    hdr = {h['key']: h['value'] for e in hs['headers'] for h in e['headers']}
    ok(hs['public'] == 'site' and not hs.get('redirects') and not hs.get('rewrites'), 'hub/firebase.json: public site, no redirects or rewrites')
    allh = {h['key']: h['value'] for e in hs['headers'] if e['source'] == '**' for h in e['headers']}
    jsonh = {h['key']: h['value'] for e in hs['headers'] if e['source'] == '**/*.json' for h in e['headers']}
    ok('X-Robots-Tag' not in allh and allh.get('Content-Security-Policy') == CSP_AUTH + "; frame-ancestors 'none'", 'hub/firebase.json: no site-wide X-Robots-Tag; header CSP = CSP_AUTH + frame-ancestors (static pages stay strict through their own meta CSP: browsers enforce both)')
    ok(jsonh == {'X-Robots-Tag': 'noindex'}, 'hub/firebase.json: JSON data files stay noindex')
    rc = json.load(open(os.path.join(ROOT, 'hub', '.firebaserc')))
    ok(hs.get('target') == 'hub' and 'site' not in hs and rc['targets']['subx-skins']['hosting']['hub'] == ['subx-hub'],
       'hub/firebase.json deploys to target hub = site subx-hub (never the subx-skins site, whose live channel is SubX Master)')
    # any other local shell copy is drift: only the declared self-hosted copy may exist
    shutil.copy(os.path.join(ROOT, 'factory', 'factory.js'), os.path.join(d, 'factory.js'))
    r = drift(d)
    ok(r['status'] == 'DRIFT', 'a second local factory.js copy in the hub = DRIFT')
    os.remove(os.path.join(d, 'factory.js'))
    # an edited self-hosted shell is drift (sha256 no longer the declared one)
    sp = os.path.join(d, SHELL_REL); orig = open(sp, 'rb').read(); open(sp, 'ab').write(b'//x\n')
    r = drift(d)
    ok(r['status'] == 'DRIFT' and any('undeclared edit' in x for x in r['findings']), 'an edited self-hosted shell = DRIFT (undeclared edit)')
    open(sp, 'wb').write(orig)
    os.remove(os.path.join(d, 'firebase.json'))  # (a strict header CSP would still cover a weak meta; test the meta alone)
    h = read(os.path.join(d, 'about.html')).replace("script-src 'self';", "script-src 'self' https:;", 1)
    open(os.path.join(d, 'about.html'), 'w').write(h)
    r = drift(d)
    ok(r['status'] == 'DRIFT' and any('about.html' in x for x in r['findings']), 'a weakened meta CSP on one hub page = DRIFT')
ok([f for f in files(SITE) if f.endswith('factory.js')] == [SHELL_REL], 'hub/site has exactly one local factory.js: the self-hosted %s' % SHELL_REL)

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
        if not f.endswith(TEXT) or f == SHELL_REL:  # the self-hosted shell is an upstream byte copy, not brand copy
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
    ok('AI-made · AI steward' in cfgj and 'Quill' not in cfgj and 'Sub' + 'X' not in cfgj, 'rename: vendored whomark config carries no brand (steward label is "AI-made · AI steward")')
    ok('data-whomark-steward="true">AI-made · AI steward' in read(os.path.join(out, 'hub.js')) and
       '.post-steward-pill[title^="Operated by Quill"]' in read(os.path.join(out, 'assets', 'whomark', 'whomark.js')),
       'rename: hub.js steward label and the whomark.js shell-pill selector follow the brand')
    d2 = os.path.join(t, 'drift', 'site'); shutil.copytree(out, d2)
    r = drift(d2)
    ok(r['status'] == 'FORK' and r['layers'].get('forkDiffLines') == 2 and not r['findings'] and not r['warnings'], 'rename: shell_drift still FORK (%s)' % r['findings'][:3])
    # topic template (HUB_COPY 4a-4e) renders every state with a dummy topic; topic text is escaped and never token-expanded
    rr = BR.Renderer(SRC, bp, os.path.join(t, 'tt')).run()
    full = {'slug': 'tide-pools', 'name': 'Tide <Pools>', 'description': 'Rock pools {{brand.name}}', 'longDescription': 'All about pools.',
            'goodPosts': 'Photos.', 'offTopic': 'Surfing.', 'rulesShort': 'Be kind.', 'status': 'hidden', 'legalProfile': 'alcohol-21'}
    th = rr.render_topic(full)
    ok('<h1>Tide &lt;Pools&gt;</h1>' in th and '&#123;&#123;brand.name&#125;&#125;' in th and '{{' not in th and '<!--' not in th, 'topic template: escaped, no token expansion, no leftovers or comments')
    ok(HEAD_RE.match(th) is not None and 'quillnest.example/z/tide-pools/' in th and 'Quillnest Labs, Inc.' in th and 'href="/z/"' in th, 'topic template: strict CSP first, topic URL under the renamed prefix, footer')
    ok('Not live yet.' in th and 'All about pools.' in th and 'Be kind.' in th and 'community guidelines' not in th and '21+ only.' in th, 'topic template: hidden + closed = not-live state; optional copy shows when present')
    ok('A Quillnest theme ·' in th and '<h2>About this theme</h2>' in th and 'A Quillnest table' not in th and 'About this table' not in th and 'Browse tables' in th,
       'topic template: header and About heading use topicNoun (theme); the live-rooms link keeps roomNoun (tables)')
    rr.cfg['topics'] = dict(rr.cfg.get('topics', {}), open=True, showDoorways=True)
    th = rr.render_topic(dict(full, legacyDomain='tidepoolchat.example'))
    ok('just getting started' in th and 'Not live yet.' not in th and 'Also reachable at tidepoolchat.example.' in th, 'topic template: open hidden state and gated doorway line')
    th = rr.render_topic(dict(full, status='quiet'))
    ok('Quiet lately. New posts welcome.' in th and 'just getting started' not in th, 'topic template: quiet badge')
    th = rr.render_topic(dict(full, status='archived'))
    ok('is resting.' in th and 'Quiet lately' not in th and 'content="noindex,nofollow"' in th, 'topic template: archived = resting, noindex')
    rr.cfg['topics']['hubNoindex'] = False
    ok('content="index,follow"' in rr.render_topic(dict(full, status='active')) and 'content="noindex,nofollow"' in rr.render_topic(dict(full, status='hidden')),
       'topic template: robots follow the status once the hub-wide noindex is lifted')
    ok('content="noindex,nofollow"' in rr.render_topic(dict(full, status='quiet')) and 'Quiet lately. New posts welcome.' in rr.render_topic(dict(full, status='quiet'))
       and 'content="noindex,nofollow"' in rr.render_topic(dict(full, status='eligible')), 'topic template: quiet and eligible stay noindex after the hub-wide noindex is lifted; quiet badge kept')
    th = rr.render_topic(dict(full, status='eligible'))
    ok('just getting started' in th and 'It can show up in search once 20 or more posts' in th and 'Quiet lately' not in th, 'topic template: eligible renders like hidden (open state)')
    rr.cfg['topics']['open'] = False
    ok('Not live yet.' in rr.render_topic(dict(full, status='eligible')), 'topic template: eligible + closed = not-live state')
    rr.cfg['topics']['open'] = True
    th = rr.render_topic({'slug': 'tide-pools', 'title': 'Tide Pools', 'description': 'd', 'status': 'hidden'})
    ok('community guidelines' in th and 'About this' not in th and '21+ only.' not in th and 'not medical' not in th, 'topic template: seed row without long copy = default rules line, no about block, no profile lines')
    for bad_t, why in (({'slug': 'Bad Slug', 'name': 'x', 'description': 'x'}, 'a bad slug'), ({'slug': 'about', 'name': 'x', 'description': 'x'}, 'a reserved slug'),
                       ({'slug': 'quillnest', 'name': 'x', 'description': 'x'}, 'the brand name as a slug'),
                       ({'slug': 'tide-pools', 'name': 'x', 'description': 'x', 'status': 'hold'}, 'a HOLD topic')):
        try:
            rr.render_topic(bad_t); ok(False, 'topic template: %s is refused' % why)
        except BR.RenderError:
            ok(True, 'topic template: %s is refused' % why)
    zt = [f for f in names if f.startswith('z/') and f != 'z/index.html']
    ok(len(zt) == len(LIVE_TOPICS) and not any(f.startswith('t/') for f in names), 'rename: all %d topic pages move to /z/<slug>/' % len(zt))
    ok(all('quillnest.example/z/' in read(os.path.join(out, f)) and 'subx' not in read(os.path.join(out, f)).replace(ALLOW[0], '').lower() for f in zt), 'rename: topic pages carry the new domain and prefix, no old brand')
    ok(all(f in s_['shell']['noShell'] for f in zt), 'rename: topic pages listed in noShell under /z/')

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
