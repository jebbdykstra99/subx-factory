#!/usr/bin/env python3
"""The partner room name lives only in hub/src/partners/usserviceanimals/config.json displayName.

A rename of that one field must change every visible use (title, header, og tags, cards, staff label).
The rendered page stays noindex and out of hub navigation while hubSlot is false."""
import json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import brand_render as BR  # noqa: E402

SRC = os.path.join(ROOT, 'hub', 'src')
SITE = os.path.join(ROOT, 'hub', 'site')
CFG = os.path.join(SRC, 'partners', 'usserviceanimals', 'config.json')
PAGE = 'partners/usserviceanimals/index.html'
EXPECTED = 'US Service Animals'
PROBE = 'Rename Probe Room'
BRIEF = (
    'Emotional support animals are not service animals under the ADA. '
    'Airlines may treat ESAs as pets. Psychiatric service dogs must be individually trained '
    'to perform disability-related work or tasks. Registration, certificates, ID cards and vests '
    'do not confer ADA public-access or airline service-animal rights. Housing accommodations are '
    'governed by separate federal and state rules; an individualized professional evaluation may '
    'provide supporting documentation, not guaranteed approval.'
)
fails = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        fails.append(msg)


def read(p):
    return open(p, encoding='utf-8').read()


cfg = json.load(open(CFG, encoding='utf-8'))
ok(cfg.get('displayName') == EXPECTED, 'config displayName is the room name')
ok(cfg.get('hubSlot') is False, 'hubSlot flag is off')
ok(read(CFG).count(EXPECTED) == 1, 'displayName is the only copy of the room name in the config file')

skip_dirs = {'.git', 'node_modules', 'hub/site', '.venv'}
hard = []
for base, dirs, files in os.walk(ROOT):
    rel_base = os.path.relpath(base, ROOT)
    dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]
    if rel_base == '.' or any(rel_base == s or rel_base.startswith(s + os.sep) for s in skip_dirs):
        continue
    for name in files:
        path = os.path.join(base, name)
        rel = os.path.relpath(path, ROOT)
        if rel == os.path.relpath(CFG, ROOT) or rel == 'test/partner_room_display_name.test.py':
            continue
        if os.path.splitext(name)[1].lower() not in ('.html', '.json', '.css', '.js', '.py', '.md', '.txt', '.svg'):
            continue
        try:
            text = read(path)
        except UnicodeError:
            continue
        if EXPECTED in text:
            hard.append(rel)
ok(not hard, 'room name is not hardcoded outside config.json (%s)' % hard[:8])

fresh = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'brand_render.py'), '--check'], capture_output=True, text=True)
ok(fresh.returncode == 0, 'brand_render --check passes (%s%s)' % (fresh.stdout.strip(), fresh.stderr.strip()))

html = read(os.path.join(SITE, PAGE))
ok('<meta name="robots" content="noindex,nofollow">' in html, 'rendered room is noindex,nofollow')
ok('<title>%s' % EXPECTED in html, 'title reads displayName')
ok('<h1 class="partner-name">%s</h1>' % EXPECTED in html, 'header reads displayName')
ok('property="og:title" content="%s"' % EXPECTED in html, 'og:title reads displayName')
ok('name="twitter:title" content="%s"' % EXPECTED in html, 'twitter title reads displayName')
ok('Sponsored by %s' % EXPECTED in html, 'disclosure reads displayName')
ok('Room sponsor: %s.' % EXPECTED in html, 'sponsor card reads displayName')
ok('%s staff' % EXPECTED not in html and 'SubX editorial' in html and 'Example partner post' in html, 'seeded byline is SubX editorial, not brand staff')
ok(BRIEF in html, 'pinned room brief uses the required wording verbatim')
ok(html.count('<article class="post') == 9, 'feed has 9 seeded posts')
ok('id="sidebar"' in html and 'class="main"' in html and 'id="right-panel"' in html, 'room shell has left nav, feed column, and right rail')
ok('partner-banner' in html and 'partner-avatar' in html, 'room has a themed banner and avatar')
ok('class="partner-chip">Sponsored' in html, 'promotional cards and posts are labeled Sponsored')

ok('usserviceanimals.org' not in html, 'room has no usserviceanimals.org href or url')
ok('/products/' not in html and '/packages/' not in html and 'checkout' not in html.lower(), 'no product, package, or checkout link')

low = html.lower()
for banned in ('ada compliant', 'ada-compliant', 'all federal ada', 'fheo', 'hud ', 'testimonial',
               'revenue', 'peekai', 'vokadots', 'dmca', 'jebb', 'j@subx', 'pays'):
    ok(banned not in low, 'rendered room does not say %r' % banned)
ok(re.search(r'(?<![0-9a-f])310(?![0-9a-f])', low) is None, 'rendered room has no 310 phone number')
scrub = low.replace('not guaranteed approval', '')
ok('guaranteed approval' not in scrub and 'guaranteed housing' not in scrub, 'no guaranteed housing approval claim')
ok('$' not in html, 'no prices')

new_files = [
    'hub/src/partners/usserviceanimals/config.json',
    'hub/src/partners/usserviceanimals/index.html',
    'hub/src/templates/partner-room.css',
    'hub/src/templates/partners.html',
    'tools/brand_render.py',
    'test/partner_room_display_name.test.py',
]
for rel in new_files:
    text = read(os.path.join(ROOT, rel))
    ok('\u2014' not in text and '\u2013' not in text, '%s has no em or en dash' % rel)

rooms = json.load(open(os.path.join(SRC, 'rooms.json'), encoding='utf-8'))
ok('usserviceanimals' not in rooms.get('featuredRooms', []) and 'usserviceanimals' not in rooms.get('roomOrder', []),
   'room is not in featuredRooms or roomOrder')
home = read(os.path.join(SITE, 'index.html'))
rooms_page = read(os.path.join(SITE, 'rooms.html'))
ok('href="/partners/usserviceanimals/"' in home and ('Sponsored by %s' % EXPECTED) in home and '>Sponsored<' in home,
   'home lists this partner room with Sponsored and the disclosure')
ok('href="/partners/usserviceanimals/"' in rooms_page and ('Sponsored by %s' % EXPECTED) in rooms_page,
   'rooms page lists this partner room above the organic list')
ok(EXPECTED not in read(os.path.join(SITE, 'about.html')), 'about does not name this partner room')
sm = read(os.path.join(SITE, 'sitemap.xml'))
ok('/partners/' not in sm, 'sitemap does not list the partner room')
site = json.load(open(os.path.join(SITE, 'site.json'), encoding='utf-8'))
ok(PAGE in site['shell']['noShell'] or ('/' + PAGE) in site['shell']['noShell'], 'partner room is a noShell page')

with tempfile.TemporaryDirectory() as t:
    src = os.path.join(t, 'src')
    shutil.copytree(SRC, src)
    cfg_path = os.path.join(src, 'partners', 'usserviceanimals', 'config.json')
    probe = json.load(open(cfg_path, encoding='utf-8'))
    probe['displayName'] = PROBE
    json.dump(probe, open(cfg_path, 'w', encoding='utf-8'))
    out = os.path.join(t, 'site')
    BR.render(src=src, out=out)
    renamed = read(os.path.join(out, PAGE))
    renamed_home = read(os.path.join(out, 'index.html'))
    ok(EXPECTED not in renamed and EXPECTED not in renamed_home, 'renamed render drops the old room name')
    ok(('Sponsored by %s' % PROBE) in renamed_home, 'renamed home disclosure follows displayName')
    ok('<title>%s' % PROBE in renamed, 'renamed title follows displayName')
    ok('<h1 class="partner-name">%s</h1>' % PROBE in renamed, 'renamed header follows displayName')
    ok('property="og:title" content="%s"' % PROBE in renamed, 'renamed og:title follows displayName')
    ok('Sponsored by %s' % PROBE in renamed, 'renamed disclosure follows displayName')
    ok('Room sponsor: %s.' % PROBE in renamed, 'renamed sponsor card follows displayName')
    ok(renamed.count(PROBE) >= 8, 'renamed name shows on title, header, tags, and cards (%d)' % renamed.count(PROBE))

print('\n%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
